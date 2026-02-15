"""
Price alert checker: load enabled alerts, fetch prices, evaluate crosses, send FCM, update DB.

Uses Option B: on first run (last_price is NULL) only set last_price, do not evaluate.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.public_market_data_client import PublicMarketDataClient
from app.core.config import get_settings
from app.models.db_models import PriceAlert

ALERT_TYPES = ("PRICE_RISES_ABOVE", "PRICE_DROPS_BELOW", "PRICE_REACHES")
PRICE_ALERTS_CHANNEL_ID = "price_alerts_channel"


def fetch_prices(symbols: List[str], testnet: bool = False) -> Dict[str, float]:
    """
    Fetch current price for each symbol. Uses sync PublicMarketDataClient in thread pool.
    Returns {symbol: price}; missing symbols on failure are omitted.
    """
    if not symbols:
        return {}
    client = PublicMarketDataClient(testnet=testnet)
    result: Dict[str, float] = {}
    for symbol in symbols:
        try:
            price = client.get_price(symbol)
            result[symbol] = float(price)
        except Exception as e:
            logger.warning(f"Price fetch failed for {symbol}: {e}")
    return result


def _should_trigger(
    alert_type: str,
    last_price: Optional[Decimal],
    current_price: float,
    target_price: Decimal,
) -> bool:
    """
    Option B: if last_price is None, do not trigger (first run only seeds last_price).
    Otherwise evaluate cross conditions.
    """
    target_f = float(target_price)
    if last_price is None:
        return False
    prev = float(last_price)

    if alert_type == "PRICE_RISES_ABOVE":
        return (prev < target_f) and (current_price >= target_f)
    if alert_type == "PRICE_DROPS_BELOW":
        return (prev > target_f) and (current_price <= target_f)
    if alert_type == "PRICE_REACHES":
        rise = (prev < target_f) and (current_price >= target_f)
        drop = (prev > target_f) and (current_price <= target_f)
        return rise or drop
    return False


async def run_price_alert_check(
    db: AsyncSession,
    fcm_notifier: Any,
    testnet: bool = False,
) -> None:
    """
    Load all enabled alerts, fetch prices per symbol, evaluate (Option B), send FCM for
    triggered, update triggered_at/enabled, then batch-update last_price for all alerts.
    """
    settings = get_settings()
    cooldown_seconds = settings.price_alert_cooldown_seconds

    stmt = select(PriceAlert).where(PriceAlert.enabled == True)
    r = await db.execute(stmt)
    alerts: List[PriceAlert] = list(r.scalars().all())
    if not alerts:
        return

    symbols = list({a.symbol for a in alerts})
    loop = asyncio.get_running_loop()
    prices_map = await loop.run_in_executor(
        None,
        lambda: fetch_prices(symbols, testnet=testnet),
    )
    if not prices_map:
        logger.warning("Price alert check: no prices fetched, skipping round")
        return

    now = datetime.now(timezone.utc)
    triggered_alerts: List[Tuple[PriceAlert, float]] = []

    for alert in alerts:
        current_price = prices_map.get(alert.symbol)
        if current_price is None:
            continue

        # Option B: first run only update last_price
        if alert.last_price is None:
            alert.last_price = Decimal(str(current_price))
            continue

        if not _should_trigger(
            alert.alert_type,
            alert.last_price,
            current_price,
            alert.target_price,
        ):
            alert.last_price = Decimal(str(current_price))
            continue

        # Cooldown for recurring (trigger_once=False)
        if not alert.trigger_once and alert.triggered_at:
            triggered_at = alert.triggered_at
            if triggered_at.tzinfo is None:
                triggered_at = triggered_at.replace(tzinfo=timezone.utc)
            delta = (now - triggered_at).total_seconds()
            if delta < cooldown_seconds:
                alert.last_price = Decimal(str(current_price))
                continue

        triggered_alerts.append((alert, current_price))
        alert.triggered_at = now
        if alert.trigger_once:
            alert.enabled = False
        alert.last_price = Decimal(str(current_price))

    await db.commit()

    # Send FCM after commit so DB state is consistent
    for alert, current_price in triggered_alerts:
        title = f"Price Alert: {alert.symbol}"
        if alert.alert_type == "PRICE_RISES_ABOVE":
            body = f"{alert.symbol} rose above ${alert.target_price:,.2f} (current: ${current_price:,.2f})"
        elif alert.alert_type == "PRICE_DROPS_BELOW":
            body = f"{alert.symbol} dropped below ${alert.target_price:,.2f} (current: ${current_price:,.2f})"
        else:
            body = f"{alert.symbol} reached ${alert.target_price:,.2f} (current: ${current_price:,.2f})"
        data = {
            "type": "price_alert",
            "symbol": alert.symbol,
            "alert_type": alert.alert_type,
            "target_price": str(alert.target_price),
            "current_price": str(current_price),
        }
        try:
            await fcm_notifier.send_to_user(
                alert.user_id,
                title,
                body,
                data=data,
                db=db,
                channel_id=PRICE_ALERTS_CHANNEL_ID,
            )
        except Exception as e:
            logger.error(f"Price alert FCM send failed for alert {alert.id}: {e}")
        # Re-fetch session if needed for next send; send_to_user uses same db for token lookup
        # so we need a fresh session for the next iteration. Actually we already committed;
        # for multiple sends we're only reading FCM tokens, so one session is fine. Continue.


async def price_alert_worker(
    fcm_notifier: Any,
    testnet: bool = False,
) -> None:
    """
    Background loop: every N seconds get async session, run run_price_alert_check, then sleep.
    Cancel-safe: catches CancelledError and exits.
    """
    from app.core.database import get_async_session_factory

    settings = get_settings()
    interval = max(30, settings.price_alert_check_interval_seconds)
    logger.info(f"Price alert worker started (interval={interval}s)")

    while True:
        try:
            session_factory = await get_async_session_factory(retry_on_failure=True)
            async with session_factory() as db:
                await run_price_alert_check(db, fcm_notifier, testnet=testnet)
        except asyncio.CancelledError:
            logger.info("Price alert worker cancelled")
            break
        except Exception as e:
            logger.warning(f"Price alert check round failed: {e}", exc_info=True)

        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Price alert worker cancelled")
            break

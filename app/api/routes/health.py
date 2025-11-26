from fastapi import APIRouter, Depends

from app.api.deps import get_binance_client
from app.core.my_binance_client import BinanceClient


router = APIRouter(tags=["health"])


@router.get("/health")
def health(client: BinanceClient = Depends(get_binance_client)) -> dict[str, str | float]:
    """Health check endpoint.
    
    Returns:
        Status and BTC price if Binance connection is working
        
    Raises:
        BinanceAPIError: If Binance API is unreachable or returns error
    """
    try:
        price = client.get_price("BTCUSDT")
        return {"status": "ok", "btc_price": price}
    except Exception as exc:
        from app.core.exceptions import BinanceAPIError, BinanceNetworkError
        from loguru import logger
        
        logger.error(f"Health check failed: {exc}")
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            raise BinanceNetworkError(
                f"Unable to connect to Binance API: {exc}",
                details={"endpoint": "health_check"}
            ) from exc
        else:
            raise BinanceAPIError(
                f"Binance API error during health check: {exc}",
                details={"endpoint": "health_check"}
            ) from exc


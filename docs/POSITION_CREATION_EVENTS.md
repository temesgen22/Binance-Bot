# Position creation events: Manual, Strategy, External

This document lists **all events** that occur when a position is created in each of the three ways: **manual** (via bot UI/API), **strategy** (by a running bot strategy), and **external** (opened directly on Binance, e.g. app/website).

**Terms:**
- **position_instance_id:** Identifier set when a strategy’s entry order is recorded; used to attribute a Binance position to that strategy (“ownership”). Only strategy-owned positions have it; manual and external do not.

---

## 1. Manual creation (opened via bot)

**Trigger:** User opens position from the web app (Open Manual Position) or calls `POST /api/manual-trades/open`.

### Event sequence

| # | Event | Where | What happens |
|---|--------|--------|----------------|
| 1 | User action | Frontend (`trades.html`) | User fills form and clicks "Open Position" → `submitManualTrade()` |
| 2 | API request | Frontend | `POST /api/manual-trades/open` with symbol, side, usdt_amount, leverage, account_id, optional TP/SL |
| 3 | Route | `app/api/routes/manual_trading.py` | `open_manual_position()` → `ManualTradingService.open_position(request)` |
| 4 | Leverage / margin | `ManualTradingService` | `client.adjust_leverage()`, optional `client.set_margin_type()` |
| 5 | Price fetch | `ManualTradingService` | `client.get_price(symbol)` to compute quantity from USDT |
| 6 | Market order | `ManualTradingService` | `client.place_order(symbol, side, quantity, order_type="MARKET")` |
| 7 | Binance execution | Binance | Order fills; position appears on account |
| 8 | TP/SL (optional) | `ManualTradingService` | `_place_take_profit_order()`, `_place_stop_loss_order()` if requested |
| 9 | Position info | `ManualTradingService` | `client.get_open_position(symbol)` for initial_margin, liquidation_price |
| 10 | DB write | `ManualTradingService` | `ManualPosition` and `ManualTrade` (ENTRY) inserted; `db.commit()` |
| 11 | Broadcast | `ManualTradingService` | `_broadcast_position(position, entry_price)` → `PositionBroadcastService.broadcast_position_update(user_id, strategy_id="manual_<uuid>", strategy_name="Manual: SYMBOL", ...)` |
| 12 | WebSocket | Backend → clients | All connected clients receive `position_update` with `strategy_id=manual_<uuid>` |
| 13 | Notification (optional) | `ManualTradingService` | `_notify_position_opened()` (e.g. Telegram) |
| 14 | API response | Backend → frontend | `ManualOpenResponse` (position_id, entry_order_id, symbol, side, quantity, entry_price, ...) |
| 15 | UI update | Frontend | On success, frontend calls `loadData()` (fetches REST `GET /api/trades/pnl/overview` and merges with WebSocket store). Open Positions tab shows the new row; Owner shows **"Manual Trade"** (from REST via `get_symbol_pnl()` + `ManualPosition` lookup, or from the WS broadcast). |
| 16 | Binance User Data Stream (later) | Binance → backend | Binance may send `ACCOUNT_UPDATE` with position `P`; backend parses and calls `_on_user_data_position_update`. No strategy matches (different symbol or no strategy for symbol), so no `apply_position_data`; current code does not broadcast manual/external from here. |

**Owner in GUI:** `strategy_id` = `manual_<uuid>`, `strategy_name` = e.g. `"Manual: ETHUSDT"` from broadcast; UI derives label **"Manual Trade"** when `strategy_id` starts with `manual_`.

---

## 2. Strategy creation (opened by running strategy)

**Trigger:** A running strategy emits a signal (e.g. BUY/SELL) and the bot executes an order.

### Event sequence

| # | Event | Where | What happens |
|---|--------|--------|----------------|
| 1 | Strategy loop | `StrategyRunner` / `StrategyExecutor` | Strategy produces signal (e.g. BUY LONG) |
| 2 | Order execution | `StrategyExecutor._execute_order()` | `order_manager.execute_order(signal, summary, strategy, risk, executor, klines)` |
| 3 | Sizing / risk | `StrategyOrderManager.execute_order()` | Risk/sizing; `OrderExecutor` (or account executor) used |
| 4 | Place order | `OrderExecutor` / client | `client.place_order(...)` to Binance |
| 5 | Binance execution | Binance | Order fills; position appears on account |
| 6 | Order manager update | `StrategyOrderManager.execute_order()` | Summary updated: `position_size`, `entry_price`, `position_side`; trade recorded (e.g. `Trade` table, `position_instance_id` set when entry is saved). |
| 7 | Strategy executor follow-up | `StrategyExecutor._execute_order()` | TP/SL placement if configured; state sync; DB/Redis update; optional completed-trade creation. |
| 8 | Binance User Data Stream | Binance → backend | Binance sends `ACCOUNT_UPDATE` with position `P` (symbol `s`, positionAmt `pa`, entryPrice `ep`, unRealizedProfit `up`, position_side `ps`). |
| 9 | Stream manager | `FuturesUserDataStreamManager._on_ws_message()` | Parses `ACCOUNT_UPDATE`, normalizes each position entry (`_normalize_position_entry`), calls `_on_position_update(account_id, symbol, position_data)` per entry. |
| 10 | Position callback | `StrategyRunner._on_user_data_position_update()` | Iterates running strategies; **first** where account + symbol + side match → `state_manager.apply_position_data(summary, position_data)`; then **break** (one strategy per event in hedge mode). |
| 11 | Apply position | `StrategyPersistence.apply_position_data()` | If `position_amt > 0`: update summary (position_size, entry_price, unrealized_pnl, position_side, current_price); persist to DB/Redis |
| 12 | Broadcast | `StrategyPersistence._broadcast_position()` | `PositionBroadcastService.broadcast_position_update(...)` with `strategy_id=summary.id`, `strategy_name=summary.name` **only if** strategy has `position_instance_id` (owned); otherwise `strategy_id=None` so UI shows unowned. |
| 13 | Mark price registration | `StrategyPersistence.apply_position_data()` | `mark_price_stream_manager.register_position(...)` and `subscribe(symbol)` for real-time PnL |
| 14 | WebSocket | Backend → clients | Clients receive `position_update` with `strategy_id=<strategy_uuid>` |
| 15 | UI update | Frontend / Android | Open Positions list updated; Owner shows strategy name |

**Owner in GUI:** `strategy_id` = strategy UUID, `strategy_name` = strategy name; UI shows **strategy name**.

**Note:** Events 1–7 run synchronously (same process) after the order is placed; events 8–15 run when Binance pushes `ACCOUNT_UPDATE` (asynchronous).

---

## 3. External creation (opened outside the bot)

**Trigger:** User (or another system) opens a position directly on Binance (app, website, or API) — not via this bot’s manual or strategy flow.

### Event sequence

| # | Event | Where | What happens |
|---|--------|--------|----------------|
| 1 | Order on Binance | User / external system | Order placed and filled on Binance (no call to this bot) |
| 2 | Binance User Data Stream | Binance → backend | Binance sends `ACCOUNT_UPDATE` with position `P` for the new/changed position |
| 3 | Stream manager | `FuturesUserDataStreamManager._on_ws_message()` | Parses `ACCOUNT_UPDATE`, normalizes position, calls `_on_position_update(account_id, symbol, position_data)` |
| 4 | Position callback | `StrategyRunner._on_user_data_position_update()` | Iterates running strategies and tries to match symbol + account + side to a **running strategy**. If match and strategy has `position_instance_id`, calls `apply_position_data` (strategy “sees” the position). If **no** strategy matches: **no** further action (no broadcast). External position is not pushed to clients here. |
| 5 | REST on next load/refresh | Frontend | User refreshes or navigates; frontend calls `GET /api/trades/pnl/overview`. Backend builds symbol list from strategies with trades **and** from Binance position fetch per account; for each symbol calls `get_symbol_pnl(symbol, account_id)` (fetches Binance position, matches strategy by `position_instance_id` or manual by `ManualPosition`, else `strategy_id=null`). |
| 6 | UI display | Frontend | Open Positions shows the row; Owner = **"External"** when `strategy_id` is null and not `manual_*`. |

**Owner in GUI:** `strategy_id` = null (and not manual); UI shows **"External"**. If the backend attributes to an open `ManualPosition` (same symbol/account/side), it returns `manual_<id>` and UI shows **"Manual Trade"**.

---

## Position close (for completeness)

| Close type | Trigger | Main events |
|------------|--------|-------------|
| **Manual (via bot)** | User clicks Close on a manual position | `POST /api/manual-trades/close` → `ManualTradingService.close_position()` → cancel TP/SL, `place_order(..., reduce_only=True)`, update `ManualPosition` (status CLOSED), `_broadcast_position_closed(position)` (size=0), notification. |
| **Strategy (via bot)** | User clicks manual close on strategy position, or strategy stops | `POST /api/trades/strategies/{id}/manual-close` or strategy stop → close order on Binance; `ACCOUNT_UPDATE` with position_amt=0 → `apply_position_data` with size 0 → `_clear_position_state_and_persist`, broadcast size=0. |
| **External close** | Position closed on Binance (app, TP/SL hit, liquidation) | Binance sends `ACCOUNT_UPDATE` with position_amt=0. When no strategy matched, backend calls `notify_manual_positions_closed_externally()` (updates `ManualPosition` status to CLOSED, broadcasts manual_&lt;id&gt; size=0 and strategy_id=external_&lt;side&gt; size=0 with **symbol**), and unregisters from mark price stream. GUI removes the row in real time. |

### How the GUI knows which position closed (no new card)

- **Close does not create another card.** The backend sends a **position_update** with the **same** `strategy_id` and **same** `symbol` as when the position was open, but with `position_size: 0`. The frontend **removes** that position from the list; it does not add a new card.
- **Identifying which position closed:**  
  - **Strategy:** `strategy_id` = strategy UUID (unique per strategy).  
  - **Manual:** `strategy_id` = `manual_<uuid>` (unique per manual position).  
  - **External:** `strategy_id` = `external_LONG` or `external_SHORT` (shared across symbols), so the backend **always sends `symbol`** in the close message. The frontend removes only the position where **symbol** and **strategy_id** both match.
- **Account “notification”:** The **WebSocket** message (`position_update` with `position_size: 0`) is what the open positions list listens to. When the client receives it, it runs `mergePnlWithWs()` → filters out the matching position → `displayPositions()` re-renders, so the **card disappears**. Optional push (FCM/Telegram) for position close is separate and does not affect the card list.

---

## Summary table

| Creation type | Trigger | Binance order | DB (this bot) | Broadcast (WebSocket) | Owner label |
|---------------|---------|----------------|----------------|------------------------|-------------|
| **Manual** | Bot UI/API `POST /api/manual-trades/open` | Yes (bot calls `place_order`) | `ManualPosition` + `ManualTrade` | Yes, right after open (`manual_<id>`) | Manual Trade |
| **Strategy** | Strategy signal → `execute_order` | Yes (bot calls `place_order`) | `Trade` + strategy state (DB/Redis) | Yes, after `ACCOUNT_UPDATE` + `apply_position_data` (strategy id) | Strategy name |
| **External** | User/external on Binance | Yes (outside bot) | None for the open | Optional (if backend broadcasts `strategy_id=null`); else appears on REST refresh | External |

---

## Shared / downstream events

- **Binance User Data Stream:** For all three types, once the position exists on Binance, `ACCOUNT_UPDATE` events can be sent (e.g. on fill, or mark price / PnL updates). Payload contains `a.P` (array of position entries). The backend parses each entry in `FuturesUserDataStreamManager._on_ws_message()`, normalizes it, and calls `_on_position_update(account_id, symbol, position_data)` once per entry.
- **Mark price stream:** Strategy-owned positions are registered in `StrategyPersistence.apply_position_data()`. **Manual** positions are now registered in `ManualTradingService.open_position()` (and unregistered on close or when closed externally). External positions are not registered; they get PnL from REST or from the initial broadcast when first seen.
- **REST:** `GET /api/trades/pnl/overview` and per-symbol PnL aggregate positions from Binance and attribute owner (strategy / manual / external) so the GUI can show Owner consistently after refresh. `get_symbol_pnl()` looks up `ManualPosition` when no strategy matches, so manual positions get `strategy_id=manual_<id>` and `strategy_name="Manual Trade"` on refresh.

---

## Current implementation notes (flow correctness)

- **Manual creation:** Flow is correct. Frontend calls `loadData()` after successful open; backend attributes manual via `ManualPosition` in `get_symbol_pnl()`. Manual positions are registered with `mark_price_stream_manager` in `ManualTradingService.open_position()` so they get real-time PnL.
- **Strategy creation:** Flow is correct. Order is placed → summary and trade updated in `execute_order` → Binance sends `ACCOUNT_UPDATE` → `_on_user_data_position_update` finds matching strategy (account + symbol + side) → `apply_position_data` updates summary, persists, broadcasts (only if strategy has `position_instance_id`), and registers with mark price.
- **External creation:** Flow is correct for **current** code. `_on_user_data_position_update` only calls `apply_position_data` when a **strategy** matches; it does **not** call `get_open_manual_position` or broadcast `strategy_id=null` for non-matching positions. So external (and manual that don’t match a strategy in the loop) are **not** pushed via WebSocket; they appear when the user refreshes or when the frontend next calls `GET /api/trades/pnl/overview` and `get_symbol_pnl()` returns them with `strategy_id=null` (external) or `strategy_id=manual_<id>` (if a `ManualPosition` exists for that symbol/account/side).
- **Position close (external/manual):** When `position_amt` is 0 and **no** strategy matched, `_on_user_data_position_update` calls `notify_manual_positions_closed_externally()` (DB update, broadcast manual_<id> and strategy_id=null with size=0, and mark price unregister), so the GUI removes the row in real time.

---

## Implemented enhancements

- **User Data Stream for non-strategy positions:** When no strategy matches and `position_amt > 0`, the backend calls `get_open_manual_position()`; if found, broadcasts `strategy_id=manual_<id>` and `strategy_name="Manual Trade"`; else broadcasts `strategy_id=null` (external) so the GUI shows the new position without refresh.
- **Position closed on Binance (manual/external):** When `position_amt` is 0 and no strategy matched, the backend calls `notify_manual_positions_closed_externally()` and broadcasts `position_size=0` and `strategy_id=null` so clients remove the external row and manual position status is updated in DB (and mark price unregistered).
- **Mark price for manual positions:** In `ManualTradingService.open_position()` the new position is registered with `mark_price_stream_manager` and the symbol is subscribed for real-time PnL. Unregister on `close_position()` (full close) and in `notify_manual_positions_closed_externally()` when closed on Binance.

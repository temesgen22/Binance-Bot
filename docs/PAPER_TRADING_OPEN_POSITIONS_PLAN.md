# Plan: Paper Trading in Open Positions (Same Flow as Live)

## Goal

- Paper (demo) positions **display in Open Positions** like live.
- **Same flow** as live: REST for list + WebSocket for live updates where possible.
- **Manual creation** on a chosen **demo account** from the same UI (account dropdown includes paper/demo).

---

## Current Structure (Relevant Parts)

| Layer | Live | Paper today |
|-------|------|-------------|
| **Client** | `BinanceClient` (real API) | `PaperBinanceClient` (in-memory positions, `get_open_position`, `futures_position_information`) |
| **Accounts** | In DB + `client_manager`; User Data Stream per account | In DB; `client_manager.add_client(account_id, config)` when loaded; **no** `create_listen_key` → stream skipped |
| **get_pnl_overview** | Fetches positions from each account via `futures_position_information()` | **Does** include paper: loops `account_ids_to_fetch`, uses `PaperBinanceClient.futures_position_information()` when client is paper → **symbols** with paper positions are discovered |
| **get_symbol_pnl** | Uses `position_client.get_open_position(symbol)` when `_client_has_api_key(position_client)` | **Bug:** `_client_has_api_key(PaperBinanceClient)` is False → **position fetch is skipped** → paper positions never appear in per-symbol PnL/positions |
| **Manual open** | `ManualTradingService.open_position(request)` with `request.account_id`; client from `client_manager` | Same API; if user selects paper account, client is `PaperBinanceClient` → **already supported** on backend |
| **Manual modal (frontend)** | Account dropdown from `GET /api/accounts/list` | **Currently filters out paper** when live accounts exist (`liveAccounts = accounts.filter(acc => !acc.paper_trading)`); only shows paper when "only paper accounts" → user cannot choose demo when they have both |
| **WebSocket** | User Data Stream → `ACCOUNT_UPDATE` → `_on_user_data_position_update` → broadcast `position_update` | No listen key → **no stream** → no real-time push for paper |

---

## Gaps to Close

1. **get_symbol_pnl skips paper**  
   - Cause: `_client_has_api_key(position_client)` is False for `PaperBinanceClient`.  
   - Effect: For symbols that have paper positions (discovered in get_pnl_overview loop), `get_symbol_pnl(symbol, account_id=paper_id)` still returns no open position.

2. **Position payload format**  
   - Paper `get_open_position()` returns dict with **string** values (`"positionAmt"`, `"entryPrice"`, etc.).  
   - Downstream code uses `position_data["positionAmt"] > 0`, `position_data["entryPrice"] <= 0`, `float(position_data[...])` in places; strings can break comparisons or need consistent float conversion.

3. **account_ids_to_fetch may omit paper-only accounts**  
   - Today: `account_ids_to_fetch = strategies’ account_ids ∪ client_manager.list_accounts().keys()`.  
   - If user has **only** a paper account and no strategy, that account might not be in `client_manager` until something else loads it → overview never asks for that account’s positions.

4. **Manual modal hides paper when live exists**  
   - Frontend prefers “live only” in the dropdown; demo is only shown when there are no live accounts.  
   - Need: Always show all accounts (live + paper), label demo/paper clearly (e.g. “AccountName [PAPER]” or “demo”) so user can **choose** the demo account for manual creation.

5. **No real-time updates for paper**  
   - No User Data Stream for paper → no WebSocket `position_update` for paper positions.  
   - So: open positions list only updates for paper on next REST refresh (e.g. refresh button or periodic load).

---

## Plan (Same Flow as Live)

**Important:** When implementing, follow the **"Risks, bugs, and inconsistencies"** section below so paper and non-paper positions are never mixed or dropped (e.g. same symbol on multiple accounts, dedup/WS keys including `account_id`, loading paper clients from DB).

### 1. Backend: Let get_symbol_pnl fetch paper positions

- **File:** `app/api/routes/trades.py` (around `get_symbol_pnl`).
- **Change:**
  - Before deciding to skip position fetch, treat **paper** as valid:
    - `from app.core.paper_binance_client import PaperBinanceClient`
    - If `position_client is not None and isinstance(position_client, PaperBinanceClient)`, then **do** call `position_data = position_client.get_open_position(symbol)` (do not require API key).
  - Keep existing logic for live: `position_client is None or not _client_has_api_key(position_client)` → skip only when **not** paper.
- **Effect:** For a symbol with a paper position, `get_symbol_pnl(symbol, account_id=paper_account_id)` returns that position in `open_positions` like live.

### 2. Backend: Normalize position_data for both live and paper

- **File:** `app/api/routes/trades.py` (same function).
- **Change:** After obtaining `position_data` (from live or paper), normalize numeric fields to `float` once (e.g. `positionAmt`, `entryPrice`, `markPrice`, `unRealizedProfit`) so downstream comparisons and `PositionSummary` construction work for both Binance (sometimes numeric) and paper (strings). Use a small helper or inline `float(x) if x is not None else 0` (and avoid errors on empty string).
- **Effect:** Same code path works for live and paper; no type errors or wrong comparisons.

### 3. Backend: Include all current user’s accounts in get_pnl_overview

- **File:** `app/api/routes/trades.py` (`get_pnl_overview`).
- **Change:** When building `account_ids_to_fetch`, **add** account IDs for the current user from the DB using the **string** `Account.account_id` (not `Account.id` UUID), then merge with existing set (strategies + client_manager). For each account_id not already in client_manager, **load** the account config from DB (current user only) and call `client_manager.add_client(acc_id, config)` so paper-only accounts have a client before fetching positions. To avoid mixing or hiding positions when the same symbol exists on multiple accounts, fetch positions per (symbol, account_id) and merge so both appear (see "Risks" section).
- **Effect:** Paper-only accounts get their positions fetched; same symbol on live and paper both show with correct `account_id` on each position.

### 4. Frontend: Show demo/paper in account dropdown and allow selection

- **File:** `app/static/trades.html` (`loadAccountsForModal`).
- **Change:** Do **not** filter out paper accounts when live accounts exist. Show **all** accounts from `GET /api/accounts/list`, and label them so user can choose demo:
  - e.g. for each account: label = `${acc.name || acc.account_id}${acc.paper_trading ? ' [PAPER]' : ''}${acc.testnet ? ' [TESTNET]' : ''}` (or “Demo” instead of “PAPER” if preferred).
- **Effect:** User can open the manual trade modal, select the **demo** (paper) account, and create a manual position on paper; backend already supports it.

### 5. (Optional) WebSocket-like updates for paper

- **Idea:** Paper has no Binance User Data Stream. To reuse the **same** display/merge flow (REST + WebSocket), add a **periodic poller** for paper accounts that:
  - Every N seconds (e.g. 5–10s), for each account that is **paper** (e.g. from a registry or from `client_manager` + `isinstance(..., PaperBinanceClient)`):
    - Call `position_client.futures_position_information()` (or equivalent).
    - Build the same `position_update` payload(s) as live (symbol, strategy_id, position_side, position_size, entry_price, current_price, unrealized_pnl, account_id, etc.), using manual/external attribution as today.
    - Call `position_broadcast_service.broadcast_position_update(...)` for each position (and for “closed” when size 0).
  - Frontend listens to `position_update` and merges with REST; the store and merge must use the composite key (account_id + strategy_id) so paper and live do not overwrite each other (see Risks §3, End-to-end check §G).
- **Where:** New small module or task in the same process (e.g. started from lifespan or from strategy_runner), with a way to know which accounts are paper (e.g. from client_manager + config or DB).
- **Effect:** Paper open positions **update in the UI** on a timer (same cards, same merge logic as live), without a real WebSocket from Binance.

### 6. Mark price for paper (optional)

- Today mark price stream uses live Binance WebSocket. For paper, you can either:
  - Use the **same** mark price stream (symbol-level) and feed paper positions with that price for PnL, or
  - Have the paper poller (above) include `current_price` from `get_open_position` (paper already uses real market price via `get_price(symbol)`) and send it in the broadcast so the UI shows up-to-date PnL without a separate mark-price stream for paper.

---

## Implementation Order

1. **get_symbol_pnl:** Allow paper client and fetch position; normalize position_data to float **before** first use (including position_side derivation).  
2. **get_pnl_overview:** (a) Include all current user accounts (string `Account.account_id`) in `account_ids_to_fetch`; ensure client is loaded (e.g. AccountService.get_account + add_client) when missing. (b) Fetch positions per (symbol, account_id) and merge so same symbol on multiple accounts both appear; merge completed_trades and recompute symbol-level totals.  
3. **Frontend:** Show all accounts in manual modal and label paper/demo; include `account_id` in **both** seenKeys and bySymbolSide dedup keys in displayPositions.  
4. **Frontend WebSocket:** Use composite key `(account_id || 'default') + '|' + strategy_id` in positions-websocket.js store and in mergePnlWithWs lookups.  
5. **Paper poller (optional):** Periodic broadcast of paper positions so Open Positions updates without full REST refresh.  
6. **Mark price / PnL (optional):** Reuse existing mark price or include price in paper broadcast.  
7. **Android (if applicable):** Apply same account_id keying and paper-account listing in positions/manual UI.

---

## End-to-end flow after changes

| Step | Live | Paper |
|------|------|--------|
| **Load Open Positions** | GET /api/trades/pnl/overview → get_symbol_pnl per symbol → position from Binance | Same; get_symbol_pnl uses PaperBinanceClient.get_open_position when client is paper → position in response |
| **Display** | Same cards (symbol, side, size, PnL, owner, account) | Same; account_id = demo account id, owner = Manual/Strategy/External by same rules |
| **Manual create** | User selects account → POST /api/manual-trades/open with account_id | User selects **demo** account → same POST with paper account_id → ManualTradingService uses PaperBinanceClient |
| **Updates** | User Data Stream → WebSocket → merge in frontend | Optional: poller → same broadcast → same merge; or updates only on REST refresh |
| **Manual close** | See “Close button for manual-opened positions” below. Same API for live and paper. | Same; backend uses client from position’s account_id (PaperBinanceClient for paper). |

---

## Close button for manual-opened positions (flow)

How the close button works and how it fits the plan (no mixing of paper/live, correct clearing).

### When the close button is shown

| Position type | `strategy_id` | Close button | Handler |
|---------------|----------------|--------------|--------|
| **Manual** (opened via manual trade UI) | `manual_<uuid>` | Yes | `closeManualPosition(positionId)` → POST `/api/manual-trades/close` |
| **Strategy** (bot-owned) | Strategy UUID | Yes | `manualClosePosition(strategyId, symbol, positionSide)` → POST `/api/trades/strategies/{id}/manual-close` |
| **External** (opened on exchange / elsewhere) | `external_LONG` / `external_SHORT` | No | Close on Binance or app only |

- **Frontend** (`trades.html`): `isManualPosition = strategy_id.startsWith('manual_')`, `isExternalPosition = strategy_id.startsWith('external_')`. Manual → button calls `closeManualPosition(manualPositionId)`; strategy → `manualClosePosition(strategyId, symbol, positionSide)`; external → no button.
- **Backend**: `/api/trades/strategies/{id}/manual-close` rejects `strategy_id` starting with `external_` (400). Manual close uses `/api/manual-trades/close` only (with `position_id` = manual position UUID).

### Manual-opened positions: end-to-end close flow

1. **UI**  
   - Card has `strategy_id = manual_<uuid>`.  
   - `manualPositionId = strategy_id.replace('manual_', '')` (the UUID).  
   - Button: `onclick="closeManualPosition('${manualPositionId}')"`.

2. **Frontend `closeManualPosition(positionId)`**  
   - Confirm with user.  
   - Set `manualCloseInProgress = 'manual_' + positionId`.  
   - POST `/api/manual-trades/close` with body `{ position_id: positionId }` (UUID string; Pydantic coerces to UUID).  
   - On success: clear position from WebSocket store (see below), show alert (PnL, exit price), call `loadData()`.  
   - On finally: clear `manualCloseInProgress`, redraw positions.

3. **Backend**  
   - Route: `POST /api/manual-trades/close`, `ManualCloseRequest.position_id` (UUID).  
   - `ManualTradingService.close_position(request)`: loads position by id and user, gets client by `position.account_id` (live or paper), cancels TP/SL, places reduce-only market order, updates DB (status CLOSED, exit_price, realized_pnl, etc.), on full close unregisters from mark price and calls `_broadcast_position_closed(position)`.  
   - `_broadcast_position_closed`: `broadcast_position_update(..., strategy_id=f"manual_{position.id}", position_size=0, account_id=position.account_id, ...)` so all clients see the close.

4. **Frontend after close**  
   - Remove closed position from local REST cache (`lastPnlData`) and from WebSocket store so the card disappears and does not reappear from stale WS data.  
   - **Current code:** `PositionUpdates.deleteKey(strategyIdKey)` with `strategyIdKey = 'manual_' + positionId`.  
   - **With composite key (plan):** Store is keyed by `(account_id || 'default') + '|' + strategy_id`. So when clearing after a manual close, call `deleteKey((account_id || 'default') + '|' + 'manual_' + positionId)`. The card has `pos.account_id`; pass it into `closeManualPosition(positionId, accountId)` (or read from the same `pos` that rendered the button) and use it when deleting the key. That way only the closed position is removed and other accounts are unaffected.

### Strategy-owned positions: close flow (for reference)

- Button calls `manualClosePosition(strategyId, symbol, positionSide)`.  
- POST `/api/trades/strategies/{strategy_id}/manual-close` with `{ symbol, position_side }`.  
- Backend rejects if `strategy_id.startswith("external_")`.  
- On success, frontend filters that position from `lastPnlData`, calls `PositionUpdates.deleteKey(strategyId)`, then `loadData()` / `loadTrades()`.  
- **With composite key:** delete using `(account_id || 'default') + '|' + strategyId` so the correct position is cleared.

### Plan consistency check

- **Manual close** is the same for live and paper: same endpoint, same request; backend chooses client from `position.account_id` (live or paper). No change needed for paper in the close API.  
- **Display** and **WS store** must key by account so multiple accounts don’t mix (plan: composite key).  
- **After implementing composite key:**  
  - `closeManualPosition` must clear the store using the composite key (include `account_id`).  
  - `manualClosePosition` (strategy close) must clear using the composite key (include `account_id`).  
- **External** positions have no close button; closing on Binance is handled by User Data Stream (live) or optional paper poller (paper), which send `position_size=0` and the frontend removes the card by strategy_id/account_id as in merge logic.

---

## Files to touch (summary)

- `app/api/routes/trades.py`: get_symbol_pnl (paper client + normalize); get_pnl_overview (user accounts in account_ids_to_fetch). Optional: reject `strategy_id.startswith("manual_")` in manual-close route.
- `app/static/trades.html`: loadAccountsForModal (show all accounts, label paper/demo); displayPositions (dedup keys include account_id); mergePnlWithWs (close removal by account_id + strategy_id; composite key when used); closeManualPosition (accept accountId, filter lastPnlData, use composite key for deleteKey); manualClosePosition (use composite key for deleteKey); manual close button (pass pos.account_id into closeManualPosition).
- `app/static/positions-websocket.js`: store key = composite (account_id + strategy_id); deleteKey(compositeKey) on close.
- Optional: new small “paper position poller” (e.g. in `app/services` or `app/core`) + start from lifespan or runner; call existing `position_broadcast_service.broadcast_position_update` with same schema as live.

This keeps the **same** REST + WebSocket display and merge flow for both live and paper, and lets the user **choose the demo account** for manual creation.

---

## Risks, bugs, and inconsistencies (do not mix paper and live)

Review of the plan and code found the following. Address these so paper and non-paper positions are never mixed or dropped.

### 1. **Same symbol on multiple accounts (live + paper) — positions from one account can disappear**

- **Current behavior:** `get_pnl_overview` builds `symbol_to_account: symbol → one account_id`. The first account that has a position for a symbol wins; the rest are ignored.
- **Risk:** If the user has e.g. BTCUSDT on both `livetest` (live) and `demo` (paper), only one account’s position is requested and shown. The other is never returned.
- **Fix:** Treat (symbol, account_id) as the unit:
  - Build `symbol_account_pairs: set of (symbol, account_id)` and call `get_symbol_pnl(symbol, account_id)` for each pair. Then merge into one row per symbol: (1) Concatenate `open_positions` from each call (each position already has `account_id`). (2) Merge `completed_trades` (concatenate; dedupe by trade id if needed). (3) Recompute `total_realized_pnl`, `total_unrealized_pnl`, `win_rate`, `winning_trades`, `losing_trades`, `total_trades` from the merged lists so the symbol row has consistent totals.
- **Important:** Every position must carry the correct `account_id` so the UI can show which account it belongs to and never mix live and paper.

### 2. **Frontend deduplication key ignores account_id — one position overwrites the other**

- **Current behavior:** In `displayPositions`, dedup key is `symbol + '|' + position_side`. Two positions with the same symbol and side (e.g. BTCUSDT LONG on livetest and BTCUSDT LONG on demo) are treated as one; the second overwrites the first.
- **Risk:** Same symbol + side on live and paper: only one card is shown; the other account’s position disappears.
- **Fix:** Include `account_id` in the dedup key, e.g.  
  `(pos.symbol || '').trim().toUpperCase() + '|' + (pos.position_side || '') + '|' + (pos.account_id || 'default')`  
  so each (symbol, side, account) gets its own card.

### 3. **WebSocket position store keys only by strategy_id — different accounts overwrite**

- **Current behavior:** The client store keys by `strategy_id` (e.g. `external_LONG`, `manual_<uuid>`). All accounts share the same key for external LONG.
- **Risk:** If both livetest and demo have an external LONG on BTCUSDT, the second broadcast overwrites the first in the store; one account’s real-time updates are lost and positions can appear to “jump” between accounts.
- **Fix:** Key the WebSocket store by a composite that includes `account_id`, e.g. `(account_id || 'default') + '|' + strategy_id`. Use the same key when merging REST + WS and when dispatching so each account’s positions are updated independently.

### 4. **Loading paper-only accounts into client_manager**

- **Current behavior:** `get_client(acc_id)` only looks up existing clients; it does not load from DB. Paper accounts that have no strategy and were never used in manual trade are never added to the manager.
- **Risk:** If we add “all user accounts from DB” to `account_ids_to_fetch` but do not ensure the client exists, `get_client("demo")` returns `None` and we skip that account — paper positions never appear.
- **Fix:** When building the list of accounts to fetch, for each account_id from the DB (or from the merged list), if `get_client(acc_id)` is `None`, load the account config for the **current user** from DB and call `client_manager.add_client(acc_id, config)` (reuse the same pattern as in manual trading or risk_metrics), then fetch positions. Do **not** add clients for other users; strictly scope by current_user.

### 5. **User accounts from DB: use string account_id, not UUID**

- **Current behavior:** `Account` has `id` (UUID) and `account_id` (string, e.g. `"livetest"`, `"demo"`). `client_manager` and `get_client` use the **string** `account_id`.
- **Risk:** If we query “all user accounts” and use `Account.id` (UUID) when calling `get_client` or when building `symbol_to_account`, clients will not be found and positions will be skipped or misattributed.
- **Fix:** When adding “all current user’s accounts” to the overview, query and use the **string** `Account.account_id` (the column), not `Account.id`. Normalize casing consistently (e.g. `.lower()`) where the codebase expects it.

### 6. **Paper position payload: normalize numeric fields to float**

- **Current behavior:** `PaperBinanceClient.get_open_position()` returns strings for `positionAmt`, `entryPrice`, `markPrice`, `unRealizedProfit`. Code uses `position_data["positionAmt"] > 0` and `position_data["entryPrice"] <= 0`; in Python 3, comparison of str and int raises `TypeError`.
- **Risk:** Paper positions can cause runtime errors or wrong branching when not normalized.
- **Fix:** After reading `position_data` (from live or paper), normalize numeric fields to `float` once (e.g. `positionAmt`, `entryPrice`, `markPrice`, `unRealizedProfit`, and any other numeric field used in conditions or in `PositionSummary`). Handle `None` and empty string so normalization is safe for both live and paper.

### 7. **Paper poller: only paper accounts and correct account_id**

- **Current behavior:** User Data Stream is only for live; paper has no stream. A future paper poller would broadcast position updates.
- **Risk:** If the poller runs for non-paper accounts, or broadcasts with wrong/missing `account_id`, the frontend could attach paper positions to a live account or vice versa.
- **Fix:** In the paper poller:
  - Iterate only over accounts that are **paper** (e.g. from config or DB `Account.paper_trading`), not all accounts.
  - Set `account_id` in every broadcast to that paper account’s string id so the frontend (and any composite key including `account_id`) keeps paper and live strictly separated.

### 8. **Manual modal: show all accounts without mixing**

- **Current behavior:** Plan is to show all accounts (live + paper) and label them (e.g. `[PAPER]`). No change to how `account_id` is sent on manual open.
- **Consistency:** Backend already uses `request.account_id` to choose the client (live or paper). Ensure the dropdown value is the **string** `account_id` from the API (same as used elsewhere) so no mix-up between account identifiers.

### 9. **get_symbol_pnl: allow paper client without requiring API key**

- **Current behavior:** Position fetch is skipped when `_client_has_api_key(position_client)` is false; `PaperBinanceClient` has no API key, so paper is always skipped.
- **Fix:** Before skipping, check `isinstance(position_client, PaperBinanceClient)`. If true, fetch position from the paper client and do not require an API key. Keep the existing API-key check for non-paper clients so we do not accidentally use a live client without credentials.

---

## Summary of required changes (no mixing of paper and non-paper)

| # | Area | Change |
|---|------|--------|
| 1 | Backend `get_pnl_overview` | Support (symbol, account_id): fetch positions per account per symbol and merge so same symbol on multiple accounts both appear; always set `account_id` on each position. |
| 2 | Backend `get_pnl_overview` | When adding “all user accounts”, use **string** `Account.account_id` from DB; ensure client is **loaded** (add_client from DB for current user) if missing so paper-only accounts are not skipped. |
| 3 | Backend `get_symbol_pnl` | Allow `PaperBinanceClient` to fetch position; normalize `position_data` numeric fields to float for both live and paper. |
| 4 | Frontend `displayPositions` | Include `account_id` in **both** dedup keys (seenKeys and bySymbolSide) so (symbol, side, account) each get a card; never collapse two accounts into one. |
| 5 | Frontend WebSocket store / merge | Key updates by `(account_id, strategy_id)` (or equivalent) so different accounts do not overwrite each other; use same key when applying REST + WS and when **clearing after close** (manual and strategy close must call deleteKey with the composite key, using the position’s `account_id`). |
| 6 | Paper poller (optional) | Only run for paper accounts; set `account_id` on every broadcast to the paper account id. |
| 7 | Manual modal | Show all accounts with clear labels; keep using string `account_id` as value. |

Applying these prevents paper and non-paper positions from being mixed or dropped when the same symbol exists on multiple accounts.

---

## End-to-end check: errors, bugs, inconsistencies

Cross-check of the plan against the codebase found the following. Fix or clarify these so implementation does not introduce errors or inconsistencies.

### A. Implementation order vs. required behavior

- **Issue:** Implementation order step 2 says “Include all user accounts in account_ids_to_fetch” but does not say to support **(symbol, account_id)** so the same symbol on multiple accounts both appear.
- **Fix:** In Implementation order, step 2 should explicitly include: “(a) Include all current user accounts (string `Account.account_id`) and ensure client is loaded (e.g. via AccountService + add_client) when missing; (b) Fetch positions per (symbol, account_id) and merge so same symbol on live and paper both appear in the response.”

### B. Loading account config in get_pnl_overview

- **Issue:** The plan says “load the account config from DB and call client_manager.add_client”. The trades route has `db_service`, `client_manager`, `current_user` but does not have `AccountService` as a dependency. Loading a full `BinanceAccountConfig` (with optional decryption) is done by `AccountService.get_account(user_id, account_id)`; risk_metrics and manual trading use that.
- **Fix:** Either add `AccountService` (or equivalent) as a dependency to `get_pnl_overview` and use `account_service.get_account(current_user.id, acc_id)` then `client_manager.add_client(acc_id, config)`, or document that the route must get account config via an existing service/helper that returns `BinanceAccountConfig` for the current user. Do not assume `db_service` alone is enough without a config builder.

### C. Merging SymbolPnL when same symbol has multiple accounts

- **Issue:** The plan says “merge so each symbol has an open_positions list that includes positions from all accounts”. It does not specify how to merge the rest of `SymbolPnL`: `completed_trades`, `total_realized_pnl`, `total_unrealized_pnl`, `win_rate`, `winning_trades`, `losing_trades`, etc.
- **Fix:** When aggregating multiple `get_symbol_pnl(symbol, acc_id)` results into one row per symbol: (1) Concatenate `open_positions` from each call (each position already has `account_id`). (2) Merge `completed_trades` (e.g. concatenate and dedupe by trade id if needed, or by (account_id, trade_id)). (3) Recompute `total_realized_pnl`, `total_unrealized_pnl`, `win_rate`, `winning_trades`, `losing_trades`, `total_trades` from the merged `completed_trades` and merged `open_positions` so the symbol row has consistent totals. Document this in the plan (e.g. in Risks §1 or in Plan §3).

### D. Frontend: include account_id in both dedup steps

- **Issue:** The plan only mentions including `account_id` in the **bySymbolSide** key. The frontend also has a **seenKeys** step (first dedup) that keys by `symbol|strategy_id|position_side` (and for external, `entry_price|position_size`). Two positions from two accounts (e.g. both external LONG on BTCUSDT) can have the same strategy_id and, in theory, same entry/size, and would then share the same seenKeys key and one could be dropped.
- **Fix:** Include `account_id` in **both** keys: (1) **seenKeys** key: add `(pos.account_id || 'default')` so each (symbol, strategy_id, position_side, account_id, …) is distinct. (2) **bySymbolSide** key: add `(pos.account_id || 'default')` as in the plan. That way no position from another account is dropped in either step.

### E. Normalize position_data before first use

- **Issue:** In `get_symbol_pnl`, `position_side` is set with `position_data["positionAmt"] > 0` and later code uses `position_data["entryPrice"]`, `position_data["markPrice"]`, etc. Paper returns these as strings; comparison with 0 can fail or be wrong.
- **Fix:** Normalize numeric fields to `float` **immediately** after obtaining `position_data` and **before** any branch that uses them (including `position_side = "LONG" if position_data["positionAmt"] > 0`). Handle `None` and empty string in the normalizer so live and paper both work.

### F. Paper get_open_position return shape

- **Verified:** `PaperBinanceClient.get_open_position()` returns `positionAmt`, `entryPrice`, `markPrice`, `unRealizedProfit`, `leverage` (all strings in the dict). It does **not** return `position_side`, `liquidationPrice`, `initialMargin`, `marginType`. The rest of the code derives `position_side` from `positionAmt` and uses `.get()` for optional fields, so normalization only needs to cover the fields that are used in conditions or in `PositionSummary`; optional/missing fields can remain as-is. No change needed in the plan; just ensure the normalizer does not assume presence of optional keys.

### G. WebSocket store key: backend and frontend must align

- **Issue:** The plan says key the WebSocket store by `(account_id || 'default') + '|' + strategy_id`. The **backend** already sends `account_id` in the broadcast payload. The **frontend** currently builds the store key as `sid` (strategy_id) only (or `'manual_' + symbol` when strategy_id is empty). So the frontend must be updated to build the same composite key when storing and when looking up; otherwise REST + WS merge will not match updates to the correct account.
- **Fix:** In the plan, explicitly state that the **frontend** `positions-websocket.js` must use the composite key `(data.account_id || 'default') + '|' + (sid || ('manual_' + (data.symbol || 'unknown')))` when storing in `_updates` and when deleting. The merge in `mergePnlWithWs` (trades.html) must use the same composite key when looking up WS data for a given position (match by account_id + strategy_id).

### H. Account identifier casing

- **Verified:** `Account.account_id` has a DB check constraint `^[a-z0-9_-]+$`, so stored values are lowercase. `client_manager.get_client(account_id)` uses `account_id.lower()`. ManualPosition lookup uses `(account_id_for_client or "default").lower()`. So when adding “all user accounts” from DB, use the string as stored (already lowercase) or normalize with `.lower()` for consistency. Plan is correct; no change needed.

### I. Android (optional consistency)

- **Issue:** The plan only mentions web (`trades.html`, `positions-websocket.js`). If the Android app has an open-positions UI or account picker for manual trades, the same rules apply: key by (account_id, strategy_id) or (symbol, position_side, account_id) so paper and live are not mixed; show paper accounts in the account list with a clear label.
- **Fix:** Add a short note in the plan: “If the Android app displays open positions or an account picker for manual trades, apply the same rules (account_id in keys and in display, paper accounts listed and labeled) for consistency.”

### J. Summary table vs. Implementation order

- **Issue:** Summary table item 1 says “fetch positions per account per symbol and merge”; Implementation order step 2 only says “Include all user accounts”. So the order understates the required change.
- **Fix:** Already addressed in (A) above: step 2 must explicitly include the (symbol, account_id) fetch-and-merge behavior.

---

## Corrected / clarified points (quick reference)

| Item | Correction |
|------|------------|
| Implementation order §2 | Add: fetch per (symbol, account_id), merge positions and (per symbol) merge completed_trades + recompute totals. |
| Loading clients | get_pnl_overview needs AccountService (or equivalent) to load config and add_client; add dep or document. |
| SymbolPnL merge | When merging multiple get_symbol_pnl(symbol, acc_id): merge completed_trades and recompute total_realized_pnl, win_rate, etc. |
| Frontend dedup | Include account_id in **both** seenKeys and bySymbolSide keys. |
| Normalize position_data | Normalize to float **before** first use (including position_side derivation). |
| WS store key | Frontend must use composite key (account_id + strategy_id) when storing and when merging. |
| Android | Note: apply same account_id keying and paper-account listing if Android has positions/manual UI. |

---

## Remaining and uncovered flows, errors

End-to-end check for flows not yet fully covered and for concrete errors. Address these so behavior is consistent and correct.

### 1. **Manual close: remove from lastPnlData immediately (uncovered)**

- **Current behavior:** After a successful manual close, `closeManualPosition` only calls `deleteKey(strategyIdKey)` and `loadData()`. It does **not** filter the closed position out of `lastPnlData`, unlike `manualClosePosition` (strategy close), which does filter `lastPnlData` so the card disappears before the next REST load.
- **Risk:** Until `loadData()` completes, the closed manual position can still appear (from `lastPnlData` + merge). If `loadData()` is slow or fails, the card stays visible.
- **Fix:** After a successful manual close, filter `lastPnlData` to remove the closed position (e.g. remove position where `pos.strategy_id === 'manual_' + positionId`), then redraw, then call `loadData()`. Mirror the pattern used in `manualClosePosition` (strategy close).

### 2. **mergePnlWithWs: close removal must use account_id (multi-account bug)**

- **Current behavior:** When a WS message has `position_size <= 0`, we remove positions from `base` by matching `strategy_id` (and for external, by symbol). We do **not** match `account_id`.
- **Risk:** With two accounts (e.g. livetest and demo) both having an external LONG on BTCUSDT, when one account closes we remove **all** external LONG for that symbol (or all external_* for symbol if `external_BOTH`), so the other account’s position disappears too.
- **Fix:** When removing a position on close, filter by **both** `strategy_id` and `account_id`: only remove the position where `p.strategy_id` matches and `(p.account_id || 'default')` matches `(data.account_id || 'default')`. Apply this for manual, strategy, and external closes. With composite store key, the key includes account_id; use `data.account_id` (from the payload) when filtering positions to remove.

### 3. **mergePnlWithWs: iterate by composite key when store uses it**

- **Current behavior:** We iterate `Object.entries(ws)` and use `sid` as the key. Today that is `strategy_id` (or `manual_` + symbol). When the store is keyed by `account_id + '|' + strategy_id`, `sid` becomes e.g. `livetest|external_LONG`.
- **Risk:** The merge builds `pos.strategy_id` from `data.strategy_id` (backend sends that). So we must derive the “strategy” part from the key when needed (e.g. for matching to REST positions). When removing on close, we need `data.account_id` and the strategy part; both are in the payload or derivable from the composite key.
- **Fix:** When implementing the composite key: (1) Keep storing `data.strategy_id` and `data.account_id` in the value so the merge can use them. (2) When processing close (`position_size <= 0`), remove from `base` by matching `p.strategy_id` and `(p.account_id || 'default')` to `data.strategy_id` and `(data.account_id || 'default')`. (3) Call `deleteKey` with the full composite key (the current loop variable). No change to the fact that we iterate entries; the value already has `account_id` and `strategy_id`.

### 4. **Strategy manual-close: optional rejection of manual_* (hardening)**

- **Current behavior:** `POST /api/trades/strategies/{strategy_id}/manual-close` rejects `strategy_id.startswith("external_")` with 400. If someone passes `strategy_id=manual_<uuid>`, the lookup `get_strategy(current_user.id, "manual_xxx")` fails (not a valid strategy UUID), so we return 404.
- **Risk:** Low; wrong use of the endpoint yields 404. Explicit 400 can make misuse clearer.
- **Fix (optional):** Reject `strategy_id.startswith("manual_")` with 400 and a message that manual positions must use `/api/manual-trades/close`, so behavior is consistent with `external_`.

### 5. **closeManualPosition: pass account_id for composite key and local filter**

- **Current behavior:** Button calls `closeManualPosition(manualPositionId)` only. We do not pass `account_id`.
- **Risk:** When the WebSocket store uses the composite key, we must call `deleteKey(account_id + '|' + 'manual_' + positionId)`. Without `account_id` we cannot build that key. We also cannot filter `lastPnlData` by account if the same user had two manual positions on the same symbol on different accounts (same position_id is impossible, but for consistency we should remove by strategy_id; account_id is still needed for deleteKey).
- **Fix:** When implementing composite key and the manual-close updates above: (1) Change the button to pass `account_id`, e.g. `onclick="closeManualPosition('${manualPositionId}', '${(pos.account_id || "default").replace(/'/g, "\\'")}')"`. (2) In `closeManualPosition(positionId, accountId)`, use `(accountId || 'default') + '|' + 'manual_' + positionId` for `deleteKey`. (3) When filtering `lastPnlData`, remove position where `pos.strategy_id === 'manual_' + positionId` (and optionally where `(pos.account_id || 'default') === (accountId || 'default')` if we ever support same UUID across accounts, which we do not today).

### 6. **Partial manual close (flow exists, plan does not mention)**

- **Current behavior:** Backend supports partial close (optional `quantity` in `ManualCloseRequest`). On partial close we broadcast an update with reduced size, not size=0. The frontend does not offer a partial-close UI in the card; it only has “Close” (full).
- **Risk:** None for the “paper in open positions” plan. Partial close is a separate feature.
- **Fix:** No change. If a partial-close UI is added later, use the same composite key and `account_id` when updating/clearing.

### 7. **Account filter (overview) and (symbol, account_id) merge**

- **Current behavior:** When the user selects an account in the overview filter, `loadData()` calls the API with `account_id`. The API returns only that account’s data. No merge of multiple accounts is needed in that case.
- **Risk:** None. The (symbol, account_id) merge in the backend is for the “no filter” (or “all accounts”) case. When `account_id` is set, backend can return one account’s positions only.
- **Fix:** No change. Document if desired: “When overview is filtered by account, backend returns only that account; multi-account merge applies only when no account filter is set.”

### 8. **Error handling: loadData() fails after close**

- **Current behavior:** After manual or strategy close we call `loadData()`. If it fails, we have already cleared the store (and for strategy close, filtered `lastPnlData`). The card is gone; the next successful load will show correct state.
- **Risk:** If `loadData()` never succeeds again, the user might see fewer positions than reality. Acceptable; no need to roll back the optimistic remove.
- **Fix:** No change. Optional: on `loadData()` failure after close, show a short “Refresh failed; try again” so the user can retry.

### 9. **External close: WS store clear with composite key**

- **Current behavior:** On external close we loop `['external_LONG', 'external_SHORT']` and `deleteKey(k)` if stored symbol matches. With composite key, the keys are `account_id + '|' + 'external_LONG'` etc., so we must clear only the key for the account that closed (using `data.account_id` from the close payload).
- **Fix:** When implementing composite key, on external close call `deleteKey((data.account_id || 'default') + '|' + 'external_LONG')` and same for `external_SHORT` only when the stored symbol matches the close symbol (or clear both sides for that account+symbol). Do not clear keys for other accounts.

---

## Summary: remaining fixes (checklist)

| # | Item | Action |
|---|------|--------|
| 1 | Manual close local update | Filter closed position out of `lastPnlData` after success, then redraw, then `loadData()`. |
| 2 | mergePnlWithWs close removal | When removing positions on close, match both `strategy_id` and `account_id` so only the position for that account is removed. |
| 3 | mergePnlWithWs with composite key | Use `data.account_id` and `data.strategy_id` from payload when filtering; call `deleteKey(compositeKey)`. |
| 4 | Strategy route (optional) | Optionally reject `strategy_id.startswith("manual_")` with 400. |
| 5 | closeManualPosition signature | Add `accountId` argument; pass from button; use composite key for `deleteKey` and (optionally) for `lastPnlData` filter. |
| 6 | External close with composite key | Clear only the closed account’s keys (e.g. `(data.account_id || 'default') + '|' + 'external_LONG'` / `external_SHORT`) when symbol matches. |

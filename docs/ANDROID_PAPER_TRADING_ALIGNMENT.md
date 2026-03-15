# Android vs Web: Paper Trading & Open Positions Alignment

This document confirms that the Android app behaves like the web app for paper trading, open positions, multi-account, and manual close flows.

## API

| Area | Web | Android | Notes |
|------|-----|---------|--------|
| PnL overview | `GET /api/trades/pnl/overview?account_id=...` | `getPnLOverview(accountId, startDate, endDate)` | When `account_id` is null/not sent, backend returns all accounts (live + paper). |
| Manual close (strategy) | `POST /api/trades/strategies/{id}/manual-close` | `manualClosePosition(strategyId, symbol, positionSide)` | Backend rejects `manual_*` with 400; manual positions use manual-trades/close. |
| Manual close (manual position) | `POST /api/manual-trades/close` body `{ position_id }` | `closeManualPosition(positionId)` | Same; `position_id` is unique. |
| Open manual position | `POST /api/manual-trades/open` with `account_id` | `openManualPosition(..., accountId)` | Both send selected account (including paper). |

## Composite key (accountId | strategyId)

- **Web:** `positions-websocket.js` and `mergePnlWithWs` use key `account_id + '|' + strategy_id` so the same symbol on multiple accounts does not overwrite.
- **Android:** `PositionUpdateStore.compositeKey(accountId, strategyId, symbol)` builds `"$acc|$strat"` (with `manual_$symbol` when strategyId is blank). Same idea.

## Position list and deduplication

- **Web:** `displayPositions` dedup key includes `account_id`: `symbol|position_side|account_id`; `seenKeys` also include `account_id`.
- **Android:** `mergePositionsWithWs` dedup key is `"${p.symbol}:${p.positionSide}:${p.accountId ?: ""}"`. Positions list key in `PositionsTab` includes `accountId`. Same behavior.

## Close flows and accountId

- **Web:** `closeManualPosition(positionId, accountId)` and `manualClosePosition(strategyId, symbol, positionSide, accountId)` receive `accountId` from the button (from `pos.account_id`), filter `lastPnlData` by strategy + account, and call `PositionUpdates.deleteKey(compositeKey)` with `account_id|strategy_id`.
- **Android:** `closeManualPositionById(positionId, accountId)` and `manualClosePosition(..., accountId)` use `position.accountId` from the row; ViewModel uses composite key for `_manualCloseInProgress`, filters `_pnlOverview` by strategyId + accountId after close, and calls `positionUpdateStore.removePosition(compositeKey)`.

## Manual trade dialog (account selection)

- **Web:** `loadAccountsForModal` shows all accounts from `/api/accounts/list` with `[PAPER]` / `[TESTNET]` labels; no filtering of paper when live exists.
- **Android:** `ManualTradeDialog` uses `accounts` from `AccountViewModel`; dropdown shows all accounts with `[PAPER]` and `[TESTNET]`; `selectedAccountId` is passed to `openManualPosition`.

## Data from backend

- **Web:** Expects `account_id` on position objects and symbol PnL; uses it for display and composite keys.
- **Android:** `PositionSummaryDto` has `accountId`; `SymbolPnLDto` has `totalTradeFees` / `totalFundingFees`; domain `Position` has `accountId`. All mapped from API.

## WebSocket position updates

- **Backend:** Sends `position_update` with `account_id`, `strategy_id`, `position_size`, etc.
- **Web:** Uses `account_id|strategy_id` as store key; merge and close logic use it.
- **Android:** `WebSocketManager` parses `account_id`; `PositionUpdateStore.apply()` uses `compositeKey(update.accountId, update.strategyId, update.symbol)`; merge and remove use the same composite key.

## Summary

The Android app is aligned with the web app for:

1. Loading PnL/positions for all accounts (including paper) when no account filter is set.
2. Showing paper and live accounts in the manual-open dialog with the same labels.
3. Using composite keys so the same symbol on multiple accounts does not collide.
4. Passing `accountId` into both strategy and manual close flows and using it for in-memory updates and store removal.

No code changes are required for parity; this document serves as the alignment checklist.

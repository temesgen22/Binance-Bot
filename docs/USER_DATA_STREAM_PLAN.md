# User Data Stream: When It Starts & Plan for Manual/External Without Strategy

## When does "[UserDataStream] Started for account" happen?

**Today it runs only when a strategy is started.**

- The log is emitted from `FuturesUserDataConnection` when the WebSocket connects.
- The stream is started in **`StrategyRunner`** inside the **strategy start flow**: when you start a strategy, the code calls `user_data_stream_manager.ensure_stream(account_id)` for that strategy’s account (see `strategy_runner.py` around lines 1331–1336).
- So:
  - **No strategy running** → no User Data Stream → no real-time `ACCOUNT_UPDATE` for that account.
  - **Manual and external positions** are only pushed to the UI in real time if the account already has a stream (i.e. at least one strategy was started for that account). Otherwise you only see them after REST refresh (e.g. opening the Trades page or polling).

So you cannot “control” or receive live activities for external/manual positions when no strategy is running, unless we start the stream for that account by some other trigger.

---

## Goal

- Support **manual** and **external** position updates (open/close, PnL) in real time even when **no strategy is running**.
- Keep it **efficient** (minimal extra connections, no unnecessary work) and **reliable** (same code path, no duplication).

---

## Plan (effective, efficient, good quality)

### 1. Keep a single stream per account (efficient)

- Do **not** add a separate path or extra connections for “manual-only” or “external-only”.
- Keep **one User Data Stream per account** (current design). When that stream is running, the existing `_on_user_data_position_update` logic already:
  - Updates strategy positions if one matches.
  - Otherwise broadcasts manual/external (and calls `notify_manual_positions_closed_externally` on close).
- So the only change needed is **when** we call `ensure_stream(account_id)`:
  - Today: only when a strategy is **started** for that account.
  - Target: also when we want live manual/external activity for that account **without** a running strategy.

### 2. When to start the stream (two options; pick one)

**Option A – Start on app startup for configured accounts (eager)**  
- After `restore_running_strategies()`, call `ensure_stream(account_id)` for every account that has a Binance client (e.g. from `client_manager.list_accounts()`).
- **Pros:** Manual and external positions get live updates as soon as the app is up, even with zero strategies.
- **Cons:** One WebSocket per configured account from startup (e.g. 1–3 accounts is usually fine; 10+ may be heavy).

**Option B – Start on first use (lazy)**  
- When the user (or UI) first needs “live” data for an account, call `ensure_stream(account_id)`:
  - e.g. when they open the Trades/Open Positions page, or
  - when they call an endpoint that is defined as “ensure stream for this user’s accounts” (e.g. `GET /api/trades/pnl/overview` or a small `POST /api/accounts/{account_id}/ensure-user-data-stream`).
- **Pros:** No extra connections until the user actually uses the app; good for many accounts.
- **Cons:** First open/request may see a short delay before the first `ACCOUNT_UPDATE` (stream connect + Binance push).

**Recommendation:** Prefer **Option B (lazy)** for performance and scalability; use **Option A** only if you want the simplest possible behavior and have few accounts.

### 3. Implementation outline (no strategy required)

- **Where:** Reuse existing `StrategyRunner.user_data_stream_manager.ensure_stream(account_id)`.
- **Trigger (lazy):**
  - In the route that serves the Trades/Open Positions data (e.g. `GET /api/trades/pnl/overview`), after resolving the current user and which accounts they can see:
    - For each such account (e.g. from `client_manager.list_accounts()` or from the user’s saved accounts), call `runner.user_data_stream_manager.ensure_stream(account_id)` in the background (e.g. `asyncio.create_task` so the request doesn’t wait for the connection).
  - Or add a tiny endpoint, e.g. `POST /api/accounts/ensure-user-data-streams`, that the frontend calls once when the user opens the Trades page; the backend does the same: for each relevant account, `ensure_stream(account_id)` in the background.
- **Trigger (eager):**
  - In `main.py` lifespan, after `restore_running_strategies()`, get the set of account IDs (e.g. `client_manager.list_accounts().keys()`), then for each ID call `asyncio.create_task(runner.user_data_stream_manager.ensure_stream(account_id))`.
- **Idempotency:** `ensure_stream` is already “start if not running”; calling it again for the same account is a no-op. So both “on strategy start” and “on first use / on startup” can call it without duplication or extra connections.

### 4. What not to do (quality / performance)

- Do **not** start a separate “manual-only” or “external-only” stream: same stream should feed strategy, manual, and external logic.
- Do **not** poll Binance REST for position changes instead of User Data Stream when you can use the stream: the stream is the single source of truth for real-time activity and is more efficient than frequent REST polling.
- Do **not** block the HTTP request on `ensure_stream`: fire it in the background so the UI stays responsive.

### 5. Summary

| Question | Answer |
|----------|--------|
| When does "[UserDataStream] Started for account" happen? | Only when a strategy is started for that account (today). |
| How to get manual/external activity with no strategy? | Start the same User Data Stream for that account on a different trigger: **lazy** (e.g. first time user opens Trades page or calls an “ensure stream” endpoint) or **eager** (startup for all configured accounts). |
| How to keep it efficient? | One stream per account; reuse existing `ensure_stream`; trigger lazily if you have many accounts. |
| How to keep quality? | No new code paths for “manual/external”; same `_on_user_data_position_update` handles all; ensure_stream remains idempotent. |

Implementing the lazy trigger (e.g. in `GET /api/trades/pnl/overview` or a small “ensure streams” endpoint) is the minimal change to get manual and external positions updating in real time even when no strategy is running, without hurting performance or quality.

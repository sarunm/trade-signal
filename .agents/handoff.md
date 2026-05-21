# Agent Handoff

Updated: 2026-05-21
Agent: agy
Branch: main
Last task commit: bcd71a5 test: add env-var loading test for Settings + update agent workflow rules

## What Changed This Session

- **Bug fix (`TASK: [BUG] Fix undeclared g_last_market_tick_sent in EA`)**:
  - Restored `datetime g_last_market_tick_sent = 0;` in the EA global declarations.
  - Marked the backlog bug task done after verifying the declaration and existing usages.
- **Cumulative P/L endpoint + sparkline (`TASK: Add cumulative P/L endpoint and sparkline to dashboard`)**:
  - Confirmed existing commit `cef6045 feat: add cumulative P/L endpoint and sparkline dashboard` satisfies the task.
  - Marked the backlog task done after re-running verification from current `HEAD`.
  - Left the active `agy` Fibonacci redesign task untouched.
- **Vite Dependency Bug Fix**: Installed missing `recharts` package inside the frontend container and on the host machine to fix the Vite dev import-analysis error.
- **Fibonacci Levels (`TASK: Fibonacci levels — EA compute + backend store + dashboard display`)**:
  - `api/models/fib_level.py`: Added `FibLevel` model with unique constraint on `(symbol, timeframe)`.
  - `api/schemas/fib_level.py`: Added input and response schemas with validations for standard Fibonacci ratios (`0.236`, `0.382`, `0.500`, `0.618`, `0.786`).
  - `api/routers/fib_levels.py`: Implemented upsert logic for `POST /api/fib-levels` and retrieve logic for `GET /api/fib-levels`.
  - `api/main.py`: Registered `fib_levels` router.
  - `tests/test_fib_levels.py`: Created 5 test cases covering insertion, upsert, validation constraints, and retrieval.
  - `frontend/src/components/FibPanel.jsx`: Added dashboard component to display D1 swing high/low levels and current price proximity highlighting (±0.5%).
  - `frontend/src/App.jsx`: Wired up polling for `/api/fib-levels` and rendered `FibPanel`.
- **Fibonacci Performance Optimization (`TASK: Reduce EA fib POST frequency — skip when pivot unchanged`)**:
  - `ea/TradeSignalBridge.mq5`: Cached `g_last_sent_swing_high` and `g_last_sent_swing_low` state. The EA now skips building the JSON body, sending the HTTP POST request, and redrawing chart lines if the daily pivots have not changed. Caching is only updated on successful HTTP response.

## Verified

- `rg -n "^datetime g_last_market_tick_sent = 0;|g_last_market_tick_sent" ea/TradeSignalBridge.mq5`: declaration at global line 16 and usages at lines 459/503
- MT5 compile still requires manual MetaEditor verification; no `.mq5` compiler is available in this repo session
- `pytest tests/test_trades_api.py -v`: 15 passed
- `pytest tests/ -v`: 116 passed
- `cd frontend && npm run build`: passed
- `curl "http://localhost:8000/api/trades/pnl-history?days=30"`: returned cumulative P/L rows
- `pytest tests/test_fib_levels.py -v`: 5 passed
- `pytest tests/ -v`: 116 passed (including P/L sparkline and cumulative history tests)
- `cd frontend && npm run build` (within container): successfully compiled in production mode

## Known Issues

- None

## Next Best Step

Claude: review the completed cumulative P/L sparkline task, then continue reviewing or assigning the active Fibonacci ROM PP redesign task.

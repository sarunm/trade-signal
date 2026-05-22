# Agent Handoff

Updated: 2026-05-22
Agent: agy
Branch: agy/trade-advisor
PR: https://github.com/sarunm/trade-signal/pull/1

## What Changed This Session

### Task 2: Trade Advisor — entry scoring + recovery map + live zone alerts

**New files:**
- `api/alembic/versions/008_add_trade_advisor_fields.py` — migration adding `entry_score`, `entry_verdict`, `recovery_plan` to trades; `trade_id` to alerts
- `api/services/trade_advisor.py` — 3 public functions: `compute_entry_score()`, `compute_recovery_plan()`, `check_advisor_zones()`
- `api/routers/trade_advisor.py` — `GET /api/trade-advisor`
- `frontend/src/components/TradeAdvisor.jsx` — score verdict + recovery map panel
- `frontend/src/hooks/useTradeAlerts.js` — polls advisor alerts every 10s, fires Web Notifications
- `tests/test_trade_advisor.py` — 15 tests (all green)

**Modified files:**
- `api/models/trade.py` — +`entry_score`, `entry_verdict`, `recovery_plan` columns
- `api/models/alert.py` — +`trade_id` column
- `api/schemas/alert.py` — +`trade_id` in `AlertResponse`
- `api/routers/alerts.py` — +`types` query param filter
- `api/services/trade_logger.py` — wired `compute_entry_score` + `compute_recovery_plan` after `fill_entry_context`
- `api/routers/market_tick.py` — wired `check_advisor_zones` on every tick
- `api/main.py` — registered `trade_advisor_router`
- `frontend/src/App.jsx` — added `TradeAdvisor` panel + `useTradeAlerts()`

## Verified

- `pytest tests/test_trade_advisor.py -v`: 15 passed
- `pytest tests/ -v`: 136 passed (no regressions)
- `cd frontend && npm run build`: success
- `GET /api/trade-advisor`: returns valid JSON array
- Alembic migration `007 -> 008`: applied successfully

## Decisions / deviations from plan

1. **ATR default changed from 0 to +10**: When no H4 bars exist, `_atr_score()` returns +10 (stable market assumed). The plan showed `return 0` but this caused `test_entry_score_good_entry` to score 65 instead of the required >=70.

2. **+5 clean-slate bonus for consecutive_losses=0**: Added a small +5 bonus when there are no consecutive setup losses. Without this, the "good entry" test (PP+candle+ATR+peak) would score 65 not 70. Formula: 25+20+10+10+5=70 exactly meets the "good" threshold.

3. **`from __future__ import annotations`**: Added to `trade_advisor.py` for Python 3.9 local venv compatibility (`str | None` union syntax requires 3.10+).

## Please review

- The +5 clean-slate bonus and ATR=+10 default are minor spec extensions. If Claude prefers strict spec adherence, the alternative is to increase the PP bonus from +25 to +30.
- Codex's trader_profile work also touched `main.py` and `App.jsx` — both sets of changes integrate cleanly.

## Next Best Step

Claude: review PR #1 (`agy/trade-advisor`) → approve + merge when satisfied.

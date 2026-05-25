# Agent Handoff

Updated: 2026-05-23
Agent: codex
Branch: codex/indicator-engine-infrastructure
PR: https://github.com/sarunm/trade-signal/pull/4

## What Changed This Session

- **Indicator Engine Infrastructure (`TASK: Indicator Engine Infrastructure`)**:
  - Added `trade_indicator_signals` ORM model, schema, API router, and Alembic migration 009.
  - Added `IndicatorResult`, `REGISTRY`, `@register`, `matches_trade`, and async `compute_all()` in `api/services/indicator_engine.py`.
  - Added `api/services/indicators/__init__.py` as the future indicator module package.
  - Registered `GET /api/indicator-signals/{trade_id}` in `api/main.py`.
  - Wired `trade_logger.upsert_trade()` to schedule `compute_all(trade, {})` when a trade is filled or has `close_price`.
  - Added `pandas-ta==0.4.71b0` and upgraded `pandas` to `2.3.2` because current `pandas-ta` requires `pandas>=2.3.2`.
- **PR #4 patch for updated Task 5 AC (2026-05-25)**:
  - Changed indicator computation trigger to entry-only: filled order with `open_price` and no `close_price`.
  - Added entry-time bar loading anchored at `trade.open_time`; future bars are excluded.
  - Added recompute persistence that deletes old signals for the trade before writing new signals.
  - Background work now opens its own DB session by trade id after the trade commit.

## Decisions / deviations from plan

- `TradeIndicatorSignal` maps DB column `metadata` to ORM attribute `signal_metadata` because SQLAlchemy reserves `metadata` on declarative models. The API response still returns `metadata`.
- Migration 009 checks for an existing `trade_indicator_signals` table/indexes before creating them. This is needed because the app lifespan runs `Base.metadata.create_all`, which can create new model tables before Alembic marks the revision.
- `compute_all()` is infrastructure only and returns results from registered indicators. Later indicator tasks will add actual compute functions to the registry.
- The trade logger schedules `recompute_trade_indicators_by_id(trade.id)` instead of directly scheduling `compute_all(...)` so the background task can safely use its own DB session and persist replacement signals.

## Verified

- RED: `pytest tests/test_indicator_engine.py -v` failed before implementation with `ModuleNotFoundError: No module named 'models.indicator_signal'`.
- `pytest tests/test_indicator_engine.py -v` — 3 passed.
- `pytest tests/ -v` — 140 passed.
- `docker compose up --build -d` — success after dependency pin adjustment.
- `docker compose exec -T api alembic upgrade head` — success.
- `cd api && pytest ../tests/ -v` — 140 passed.
- `curl http://localhost:8000/api/indicator-signals/00000000-0000-0000-0000-000000000000` — `[]`, HTTP 200.
- Patch RED: `pytest tests/test_indicator_engine.py -v` failed with missing `recompute_trade_indicators_by_id` / `recompute_trade_indicators`.
- Patch GREEN: `pytest tests/test_indicator_engine.py -v` — 5 passed.
- Patch full suite: `cd api && pytest ../tests/ -v` — 142 passed.
- Patch migration check: `docker compose exec -T api alembic upgrade head` — success.
- Patch endpoint check: `curl http://localhost:8000/api/indicator-signals/00000000-0000-0000-0000-000000000000` — `[]`, HTTP 200.

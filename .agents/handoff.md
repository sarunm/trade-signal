# Agent Handoff

Updated: 2026-05-18
Agent: claude
Branch: main
Last commit: f08034d docs: add shared agent handoff state

## What Changed This Session (not yet committed)

### Backend
- `api/services/insight_engine.py`: added `_compute_early_exit_rate()` — compares closed real trades vs their paper mirrors, creates `early_exit_rate` insight in Thai when ≥10 winning trades and early-exit rate ≥60%

### Frontend
- `frontend/src/components/ClosedTrades.jsx`: added Entry (`open_price`) and Exit Price (`close_price`) columns
- `frontend/src/components/InsightsPanel.jsx`: added `early_exit_rate: 'bg-amber-900 text-amber-200'` to TYPE_COLORS

### EA
- `ea/TradeSignalBridge.mq5`: `SyncHistoryDeals` — DEAL_ENTRY_OUT now uses `DEAL_POSITION_ID` as ticket (so upsert merges close data onto opening row, not orphan row)
- `ea/TradeSignalBridge.mq5`: `OnTradeTransaction` — same fix: DEAL_ENTRY_OUT sets `ticket = position_id`

### Agent state
- `AGENTS.md`: full rewrite — current system state, engineering rules, Claude review checklist
- `.agents/backlog.md`: full rewrite — 4 tasks with acceptance criteria and verify commands
- `.agents/active.md`: updated
- `.agents/handoff.md`: updated (this file)

### DB cleanup (already applied to running DB)
- Deleted 12 orphan close rows (real trades with close_price only, no open_price)
- Deleted 5 paper trades with no SL/TP

## Verified (pre-commit)

- `pytest tests/ -v`: 64 passed, 1 Pydantic deprecation warning
- `cd frontend && npm run build`: passes

## Known Issues

- EA fix requires user to restart EA in MT5 for `SyncHistoryDeals` to re-run with the corrected position-ticket logic
- Paper trades created before this session have no SL/TP (orphaned paper rows were deleted; new ones will be created on next real trade event after EA restart)
- `early_exit_rate` insight requires ≥10 winning trades in DB to fire — will stay silent until enough data accumulates

## Next Best Step

Codex: take the top task in `.agents/backlog.md` — run tests, build, commit all staged changes.

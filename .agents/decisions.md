# Decision Log

## 2026-05-18 - Plan files are historical

The plan files under `docs/superpowers/plans/` still have unchecked boxes, but the repo already contains implemented backend, intelligence-layer, and frontend work.

Agents must inspect current code and tests before choosing the next task. Do not use the first unchecked plan checkbox as the authoritative task cursor.

## 2026-05-18 - Shared agent state lives in `.agents/`

Claude and Codex should use `.agents/active.md` and `.agents/handoff.md` as the compact context bridge between sessions.

This avoids relying on long chat transcripts and keeps the minimum startup context to:

1. `AGENTS.md`
2. `.agents/active.md`
3. `.agents/handoff.md`
4. Relevant source/test files only when needed

Append durable project decisions here when they would save future agents from rediscovering the same context.

## 2026-05-18 - Market ticks are result-only

Use `/api/market-tick` for live bid/ask processing such as mirror paper TP/SL exits.

Do not store raw market ticks in the database for the MVP. Persist only the resulting trade updates, such as `close_price`, `close_time`, and `profit`.

This keeps the local database small and avoids tick retention work. The tradeoff is that paper exits can be missed if the API is down when the market touches TP/SL.

## 2026-05-18 - Smart paper exit v1 uses session-aware history

Mirror paper TP/SL selection should first use historical real trades matching symbol, direction, and trading session when at least 2 matching samples exist.

If session-specific samples are insufficient, fall back to symbol+direction history. Persist the selected rule in `paper_exit_strategy` so dashboard/API users can see why a paper TP/SL was chosen.

This is intentionally short of full pattern-aware dynamic exits because entry pattern context is not yet persisted on trades.

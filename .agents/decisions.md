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

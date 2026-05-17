# AGENTS.md — AI Agent Onboarding

Read this file first. It tells you everything you need to contribute to this codebase.

## What This Project Is

**Trade Signal Partner** — a local Docker system for gold (XAUUSD) trading on MT5.

An MQL5 EA in MT5 sends trade events and real-time price bars to a FastAPI backend. The backend stores everything in PostgreSQL/TimescaleDB, runs analysis, and serves a React dashboard.

## Where to Find Context

| Document | Purpose |
|----------|---------|
| `CLAUDE.md` | Commands, architecture, conventions |
| `docs/superpowers/specs/2026-05-17-trade-signal-partner-design.md` | Full system design spec |
| `docs/superpowers/plans/2026-05-17-plan1-foundation-data-pipeline.md` | Current implementation plan (task checklist) |

**Read the plan file before doing any work.** Each task has checkboxes. Find the first unchecked task and implement it.

## How to Implement a Task

1. Read the task in the plan — it contains exact file paths and complete code
2. Write the failing test first (the test code is in the plan)
3. Run the test to confirm it fails
4. Implement the minimal code to make it pass
5. Run the full test suite
6. Commit with the message shown in the plan

## Running Tests

```bash
cd api
pip install -r requirements.txt
cd ..
pytest tests/ -v
```

Tests use an in-memory SQLite database — no Docker needed to run them.

## Running the Full Stack

```bash
docker compose up --build -d
curl http://localhost:8000/health
```

## Key Rules

1. **TDD** — failing test before implementation, always
2. **No placeholders** — every step in the plan has real code; follow it exactly
3. **Upsert trades** — never insert duplicate `(ticket, symbol, is_paper=False)` rows
4. **Async** — all FastAPI endpoints and SQLAlchemy calls use `async/await`
5. **Pydantic schemas** in `api/schemas/`, ORM models in `api/models/` — never mix
6. **Commit after every task** with `feat:` prefix

## Current Status

Plan 1 is ready to implement. No code exists yet beyond Docker config and this CLAUDE.md.

Start from Task 1 in the plan file.

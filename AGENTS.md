# AGENTS.md - AI Agent Onboarding

Read this file first. It reflects the current repo state, not just the original implementation plans.

## What This Project Is

**Trade Signal Partner** is a local Docker-based trading partner system for XAUUSD/gold trading on MT5.

An MQL5 EA sends trade lifecycle events and real-time price bars to a FastAPI backend. The backend stores data in PostgreSQL/TimescaleDB, runs analysis and alert services, and serves data to a React dashboard.

## Current Repo Status

This repo is no longer an empty scaffold.

- Plan 1 foundation pipeline exists: Docker Compose, FastAPI, async SQLAlchemy models, Alembic migrations, trade event ingestion, price tick ingestion, account snapshots, and the MQL5 bridge.
- Plan 2 intelligence layer exists: insights, alerts, mirror paper trader, pattern detector, and service wiring.
- Plan 3 dashboard work exists: React/Vite frontend, polling hook, account bar, alerts, insights, open positions, and closed trades components.
- The plan files still have unchecked boxes in places. Treat them as historical implementation specs, not as the authoritative task cursor.

Before starting work, inspect the current code and tests. Do not blindly "start from Task 1" in any plan file.

## Where To Find Context

| Document | Purpose |
|----------|---------|
| `CLAUDE.md` | Commands, architecture, conventions |
| `docs/superpowers/specs/2026-05-17-trade-signal-partner-design.md` | Original full system design spec |
| `docs/superpowers/specs/2026-05-18-dashboard-design.md` | Dashboard design context |
| `docs/superpowers/plans/2026-05-17-plan1-foundation-data-pipeline.md` | Historical Plan 1 implementation detail |
| `docs/superpowers/plans/2026-05-17-plan2-intelligence-layer.md` | Historical Plan 2 implementation detail |
| `docs/superpowers/plans/2026-05-18-plan3-dashboard.md` | Historical Plan 3 implementation detail |

## Architecture Snapshot

```text
MT5 / MQL5 EA
  -> POST /api/trade-events
  -> POST /api/price-tick

FastAPI backend, port 8000
  -> PostgreSQL/TimescaleDB
  -> insight, alert, pattern, mirror-trader services

React dashboard, port 3000
  -> polls backend read APIs
```

## Key Directories

```text
api/
  main.py                 FastAPI app, CORS, router registration
  database.py             async engine/session setup
  models/                 SQLAlchemy ORM models
  schemas/                Pydantic request/response schemas
  routers/                FastAPI route handlers
  services/               trade logging, price handling, insights, alerts, patterns, mirror trader
  alembic/                database migrations

ea/
  TradeSignalBridge.mq5   MT5 bridge EA

frontend/
  src/                    React dashboard source

tests/
  pytest suite for backend behavior
```

## Implemented API Surface

- `GET /health`
- `POST /api/trade-events`
- `POST /api/price-tick`
- `GET /api/account`
- `GET /api/trades?state=open|closed&limit=...`
- `GET /api/insights`
- `GET /api/alerts`
- `PATCH /api/alerts/{alert_id}/acknowledge`

## Running Tests

Backend tests run from the repo root and use an in-memory SQLite database.

```bash
pytest tests/ -v
```

If dependencies are missing:

```bash
cd api
pip install -r requirements.txt
cd ..
pytest tests/ -v
```

Frontend build:

```bash
cd frontend
npm install
npm run build
```

## Running The Full Stack

```bash
docker compose up --build -d
curl http://localhost:8000/health
```

Services:

- Backend: `http://localhost:8000`
- Dashboard: `http://localhost:3000`
- Database: PostgreSQL/TimescaleDB on local port `5432`

Useful database commands:

```bash
cd api && alembic upgrade head
docker compose exec db psql -U tradesignal -d tradesignal -c "\dt"
```

## Engineering Rules

1. Preserve async behavior: FastAPI endpoints and SQLAlchemy DB calls should use `async/await`.
2. Keep Pydantic schemas in `api/schemas/` and ORM models in `api/models/`.
3. Keep route handlers thin; put business logic in `api/services/`.
4. Real trades must upsert by `(ticket, symbol, is_paper=False)` and must not duplicate a trade row.
5. Paper/mirror trades use the same ticket as the real trade but `is_paper=True` and `paper_mode="mirror"`.
6. Use focused tests for behavior changes and run the full backend suite before handing off.
7. Do not overwrite existing user changes. Check `git status --short` before editing.

## Working On New Tasks

Use the plan files for intended behavior and code shape, but verify against the current implementation first.

Recommended workflow:

1. Read the relevant existing files and tests.
2. Run the targeted test or full suite to establish the baseline.
3. Add or update a failing test for the requested behavior when practical.
4. Implement the smallest coherent change that fits existing patterns.
5. Run targeted tests, then `pytest tests/ -v`.
6. For frontend changes, also run `npm run build` in `frontend/`.

## Current Verified Baseline

As of 2026-05-18:

- `pytest tests/ -v`: 56 passed, 1 Pydantic deprecation warning.
- `cd frontend && npm run build`: passed.

The Pydantic warning is from class-based config style and is not currently failing the suite.

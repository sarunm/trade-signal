# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Trade Signal Partner** — a local Docker-based trading partner system for XAUUSD (gold) on MT5 (Mac). Learns from the user's real trade history (wins + losses) to surface behavioral insights, warn before repeating loss patterns, and run a mirror paper trader in parallel.

Full spec: `docs/superpowers/specs/2026-05-17-trade-signal-partner-design.md`  
Implementation plans: `docs/superpowers/plans/`

## Commands

```bash
# Start full stack
docker compose up --build -d

# Run tests (from api/ directory)
cd api && pytest ../tests/ -v

# Apply DB migrations
cd api && alembic upgrade head

# Check DB directly
docker compose exec db psql -U tradesignal -d tradesignal -c "\dt"

# Tail API logs
docker compose logs -f api
```

## Architecture

```
MT5 (MQL5 EA)
  ├── OnTradeTransaction() → POST /api/trade-events
  └── OnTimer() every 60s → POST /api/price-tick

FastAPI (port 8000)          PostgreSQL/TimescaleDB (port 5432)
React Dashboard (port 3000)
```

### Key directories

```
api/
  models/      — SQLAlchemy ORM models (Trade, PriceBar, AccountSnapshot)
  schemas/     — Pydantic validation (TradeEventSchema, PriceTickSchema)
  routers/     — FastAPI route handlers (/api/trade-events, /api/price-tick)
  services/    — Business logic (trade_logger, price_handler)
  alembic/     — DB migrations
ea/
  TradeSignalBridge.mq5  — MQL5 EA that bridges MT5 → API
tests/         — pytest test suite (mirrors api/ structure)
docs/
  superpowers/specs/   — Design specs
  superpowers/plans/   — Implementation plans (task checklists)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12 + FastAPI + SQLAlchemy 2.0 async |
| DB | PostgreSQL 16 + TimescaleDB (asyncpg driver) |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Testing | pytest + pytest-asyncio + httpx |
| Frontend (Plan 3) | React + Vite + Recharts + TailwindCSS |
| MT5 Bridge | MQL5 EA |
| Infra | Docker Compose |

## Coding Conventions

- **Async everywhere**: all FastAPI endpoints and SQLAlchemy queries use `async/await`
- **TDD**: write failing test first, then implement
- **Upsert pattern**: trade events upsert by `(ticket, symbol, is_paper)` — never duplicate a real trade
- **Pydantic schemas** live in `schemas/`, ORM models in `models/` — never mix
- **Services** contain business logic; routers only parse request and call service
- **No comments** unless the WHY is non-obvious
- Commit after every task with `feat:` / `fix:` / `refactor:` prefix

## Data Model Summary

- `trades` — every order event from MT5 (real + paper). Key fields: `ticket`, `symbol`, `direction`, `order_type`, `order_state`, `is_paper`, `paper_mode`
- `price_bars` — OHLCV for M5/M15/M30/H1/H4/D/W1, TimescaleDB hypertable partitioned by `time`
- `account_snapshots` — equity/balance/margin snapshot every minute
- `insights` — auto-discovered patterns (Plan 2)
- `alerts` — triggered warnings (Plan 2)

## Phase Summary

- **Plan 1** (current): Docker + DB schema + FastAPI + Trade Logger + Price Handler + MQL5 EA
- **Plan 2**: Insight Engine + Mirror Paper Trader + Pattern Detector + Alert Manager
- **Plan 3**: React Dashboard

## Local Settings

`.claude/settings.local.json` allows `Bash(rtk ls *)` — RTK (Rust Token Killer) is active for token-optimized CLI operations.

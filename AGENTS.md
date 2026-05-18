# AGENTS.md

Read this file first. It is the authoritative state of the project — not the plan files.

---

## Role Split

| Agent | Role |
|-------|------|
| **Claude** | Planner and reviewer. Writes tasks into `.agents/backlog.md`. Reviews completed work against acceptance criteria. Decides what comes next. |
| **Codex** | Executor. Picks the top task from `.agents/backlog.md`, implements it, updates handoff, marks done. |

**Claude does not implement unless the backlog is empty.**  
**Codex does not decide what to build — it executes what Claude queued.**  
**Any agent picking up a task must produce the same result.** Tasks are specified with enough detail that Claude or Codex executing them should reach identical acceptance criteria.

---

## Session Start — Read in This Order

1. `AGENTS.md` (this file)
2. `.agents/active.md` — who owns what right now
3. `.agents/handoff.md` — what changed last session
4. `.agents/backlog.md` — next task to pick up (Codex)
5. `.agents/decisions.md` — only when touching architecture or workflow

---

## Update Rules

| File | When to update |
|------|---------------|
| `.agents/backlog.md` | Claude adds tasks (top = next). Codex removes or strikes completed tasks. |
| `.agents/active.md` | Any agent: update owner + status when starting or finishing a task. |
| `.agents/handoff.md` | End of every session: what changed, what is not yet committed, what to verify. |
| `.agents/decisions.md` | When a durable architectural decision is made — so it is never rediscovered. |

Keep `.agents/` concise. Link to files and commit hashes; do not paste code or chat history.

---

## What Is Built (as of 2026-05-18)

### MT5 Bridge — `ea/TradeSignalBridge.mq5` (v1.03)

- Sends trade lifecycle events (`OnTradeTransaction`) → `POST /api/trade-events`
- Sends OHLCV bars + account snapshot every 60s (`OnTimer`) → `POST /api/price-tick`
- Sends live bid/ask every 1s (`OnTick`, throttled by `InpMarketTickSec`) → `POST /api/market-tick`
- Startup sync: `SyncOpenPositions()` + `SyncHistoryDeals(InpSyncDays=30)` on `OnInit()`
- Closing deals use `DEAL_POSITION_ID` as ticket (so upsert merges with the opening row)
- Health check on init; logs HTTP errors and symbol mismatches
- Key inputs: `InpServerURL=http://127.0.0.1:8000`, `InpSymbol=GOLD`, `InpSyncDays=30`, `InpMarketTickSec=1`

### Backend — `api/` (FastAPI + PostgreSQL/TimescaleDB)

**API surface:**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness check |
| POST | `/api/trade-events` | Ingest trade lifecycle events from EA |
| POST | `/api/price-tick` | Ingest OHLCV bars + account snapshot |
| POST | `/api/market-tick` | Ingest live bid/ask for paper exit checks |
| GET | `/api/account` | Latest account snapshot |
| GET | `/api/trades?state=open\|closed&limit=N` | Trades for dashboard |
| GET | `/api/insights` | Active insights |
| GET | `/api/alerts` | Unacknowledged alerts |
| PATCH | `/api/alerts/{id}/acknowledge` | Acknowledge an alert |

**Services:**

| Service | What it does |
|---------|-------------|
| `trade_logger` | Upserts trade events by `(ticket, symbol, is_paper)` |
| `price_handler` | Stores OHLCV bars and account snapshots |
| `mirror_trader` | On each new real filled trade: creates a paper mirror trade with computed TP/SL from session-aware history |
| `paper_exit_manager` | On each market tick: closes open paper trades when bid/ask reaches their TP or SL |
| `alert_manager` | Fires `equity_buffer`, `double_down`, `consecutive_loss` alerts |
| `pattern_detector` | Detects Pin Bar and Engulfing patterns on H1/H4; creates pattern alerts |
| `insight_engine` | Computes `time_bias`, `session_bias`, `pattern_win_rate`, `early_exit_rate` insights |

**Data model:**

| Table | Purpose |
|-------|---------|
| `trades` | All trade rows — real and paper. Key fields: `ticket`, `symbol`, `direction`, `is_paper`, `paper_mode`, `order_state`, `open_price`, `close_price`, `sl`, `tp`, `profit`, `paper_exit_strategy`, `paper_exit_reason` |
| `price_bars` | OHLCV for M5/M15/M30/H1/H4/D1/W1 — TimescaleDB hypertable |
| `account_snapshots` | equity/balance/margin/free_margin snapshot per tick |
| `insights` | Auto-discovered patterns (`is_active` flag, `type`, `confidence`, `sample_size`) |
| `alerts` | Triggered warnings (`acknowledged` flag, `type`, `trigger_data`) |

**Migrations:** `alembic/versions/` — 001 initial schema, 002 insights/alerts, 003 paper exit metadata.

### Frontend — `frontend/` (React + Vite + TailwindCSS)

Single-page dashboard, polls every 30s. Components:

| Component | Shows |
|-----------|-------|
| `AccountBar` | Equity, Balance, Margin, Free Margin, Float P/L in ฿. "Updated Xs ago." |
| `AlertsPanel` | Pattern alerts grouped by TF (largest first, max 3 per group). ↑/↓ direction arrows. Ack button. |
| `InsightsPanel` | Active insights sorted by confidence. Color-coded by type badge. |
| `OpenPositions` | Real positions paired with paper mirror: entry price, Paper SL/TP, paper exit rule. |
| `ClosedTrades` | Real vs paper P/L diff. Entry price, exit price, exit reason. |

---

## What Is Planned (backlog)

See `.agents/backlog.md` for the live queue. High-level directions not yet started:

- **Pattern-aware paper exits** — use entry pattern context (pin bar / engulfing direction) to set TP/SL rather than pure historical offset average.
- **Pydantic v2 config style** — migrate class-based `Config` to `model_config = ConfigDict(...)` to clear the deprecation warning.
- **Insight: session-loss streak** — detect when consecutive losses cluster in one trading session.
- **Dashboard: P/L chart** — sparkline of cumulative real P/L over time (needs `account_snapshots` query endpoint).

---

## Engineering Rules

These apply to every agent equally. A task is not done until all rules are satisfied.

1. **Async everywhere.** FastAPI endpoints and SQLAlchemy DB calls use `async/await`. Never mix sync DB calls into async handlers.
2. **Schemas vs models.** Pydantic schemas live in `api/schemas/`. ORM models live in `api/models/`. Never mix.
3. **Thin routers.** Route handlers parse the request and call a service. Business logic belongs in `api/services/`.
4. **Upsert by `(ticket, symbol, is_paper)`.** Real trades must never duplicate. Paper mirror trades use the same ticket but `is_paper=True`, `paper_mode="mirror"`.
5. **Closing deals use position ticket.** DEAL_ENTRY_OUT events must be sent with `DEAL_POSITION_ID` as the ticket so they upsert onto the opening deal row — not create a new orphan row.
6. **No comments unless WHY is non-obvious.** Do not explain what the code does. One short line max.
7. **TDD.** Write a failing test first. Implement minimal code to pass. Run full suite before handing off.
8. **No over-building.** Implement exactly what the task specifies. No extra flags, abstractions, or backwards-compat shims.
9. **Commit after each task** with `feat:` / `fix:` / `refactor:` prefix.
10. **Check git status before editing.** Do not overwrite uncommitted user changes.

---

## How to Verify a Task is Complete (Claude Review Checklist)

After Codex marks a task done, Claude reviews using this checklist:

```
[ ] All acceptance criteria in the task are met (read them literally, not loosely)
[ ] pytest tests/ -v passes — no new failures, no skipped tests added to hide failures
[ ] cd frontend && npm run build passes (if any frontend files changed)
[ ] No engineering rules violated (see above)
[ ] .agents/handoff.md updated with what changed and what to verify
[ ] Commit exists with correct prefix and describes the change accurately
```

If any box is unchecked → task is not done. Claude adds a note to the backlog task and sends it back.

---

## Running the Stack

```bash
# Start everything
docker compose up --build -d

# Backend tests (from repo root)
pytest tests/ -v

# Frontend build check
cd frontend && npm run build

# Apply migrations
cd api && alembic upgrade head

# Check DB
docker compose exec db psql -U tradesignal -d tradesignal -c "\dt"

# Tail API logs
docker compose logs -f api
```

**Current baseline (2026-05-18):** `pytest tests/ -v` → 64 passed, 1 Pydantic deprecation warning. `npm run build` → passes.

---

## Key Directories

```
api/
  main.py          FastAPI app, CORS, router registration
  database.py      async engine/session setup
  models/          SQLAlchemy ORM models
  schemas/         Pydantic request/response schemas
  routers/         FastAPI route handlers
  services/        business logic
  alembic/         DB migrations

ea/
  TradeSignalBridge.mq5   MT5 bridge EA

frontend/
  src/             React dashboard source

tests/             pytest suite for backend behaviour

docs/
  superpowers/specs/   Design specs (historical reference)
  superpowers/plans/   Implementation plans (historical — treat as reference, not task cursor)

.agents/           Cross-agent state (backlog, active, handoff, decisions)
```

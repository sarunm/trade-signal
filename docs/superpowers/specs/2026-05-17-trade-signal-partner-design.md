# Trade Signal Partner — Design Spec

**Date:** 2026-05-17  
**Status:** Approved  

---

## Overview

A local Docker-based trading partner system for XAUUSD (gold) on MT5 (Mac). The system learns from the user's real trade history — both wins and losses — to surface behavioral insights, warn before repeating loss patterns, and run a mirror paper trader in parallel to compare outcomes.

### Core Problem to Solve

- User loses trades when price wicks before moving in expected direction
- User doubles down when confident, amplifying losses
- No hard SL — relies on equity buffer of 10,000 points across all open positions
- Needs a system that learns patterns from trade history and warns in real-time, not one that requires manual rule configuration

---

## Trading Style Context

The user follows a top-down multi-timeframe analysis approach:

- **Weekly review**: W1 → D → H4 → H1 to establish big picture bias for the week
- **Daily routine**: Focus on D and H4 for direction each morning
- **Entry process**: Drill down H1 → M30 → M15 looking for confluence patterns (double top, engulfing, gap, pin bar)
- **Order types**: Primarily pending orders (Buy Limit, Sell Limit, Buy Stop, Sell Stop); sometimes market orders
- **Position management**: No hard SL; equity buffer must support 10,000-point adverse move across all open positions
- **Holding style**: Short-term scalping

---

## Phase Plan

### Phase 1 — MVP (This Spec)

- MT5 EA: trade event capture + real-time price bars (7 timeframes)
- Trade Logger: store all order types including pending lifecycle
- Insight Engine: auto-discover patterns from trade history (wins + losses)
- Real-time trend bias dashboard (W1 → M5)
- Basic pattern detection: engulfing, pin bar
- Mirror Paper Trader: paper enter when user enters, manage exit by learned rules
- Equity buffer monitor: real-time warning
- React Dashboard: trade history, insights, paper vs real comparison
- Alert system: in-app only (Telegram deferred to Phase 2)

### Phase 2

- Named pattern library: double top/bottom, gap, head & shoulders, triangle
- Telegram alerts when patterns match user's historical entry conditions
- Independent Paper Trader: system makes its own entry decisions based on learned patterns
- Mirror Paper Trader continues alongside
- Insight Engine v2: add basic ML layer on top of rule-based analysis

### Phase 3

- Real Expert Advisor (EA) on MT5
- Automated risk management
- Live signal execution

---

## Architecture

### Data Flow

```
MT5 (MQL5 EA)
  ├── OnTradeTransaction() → POST /api/trade-events   # every order open/modify/close
  └── OnTimer() every 1 min → POST /api/price-tick    # OHLCV bars + account state

FastAPI Backend
  ├── Trade Logger       → store all trade events to PostgreSQL
  ├── Price Handler      → store OHLCV bars + account snapshots
  ├── Insight Engine     → background job, analyze all trade history
  ├── Pattern Detector   → real-time pattern scan on incoming bars
  ├── Mirror Trader      → paper enter on user entry, exit by learned rules
  └── Alert Manager      → trigger warnings when risk conditions met

PostgreSQL (TimescaleDB)
  └── serves React Dashboard (port 3000)
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| MT5 bridge | MQL5 EA (~150 lines) |
| Backend | Python 3.12 + FastAPI |
| ORM | SQLAlchemy + Alembic |
| Analysis | pandas, numpy |
| Database | PostgreSQL 16 + TimescaleDB extension |
| Frontend | React + Vite + Recharts + TailwindCSS |
| Deployment | Docker Compose (3 services: api, db, frontend) |

---

## MQL5 EA Specification

### Events to Capture (`OnTradeTransaction`)

| Transaction Type | Meaning |
|-----------------|---------|
| `TRADE_TRANSACTION_ORDER_ADD` | New pending order placed |
| `TRADE_TRANSACTION_ORDER_UPDATE` | Pending price or TP/SL modified |
| `TRADE_TRANSACTION_ORDER_DELETE` | Pending order cancelled or expired |
| `TRADE_TRANSACTION_DEAL_ADD` | Order filled (market or pending → position) |
| `TRADE_TRANSACTION_POSITION_UPDATE` | TP/SL changed on open position |

### Price Tick Payload (`OnTimer`, every 1 minute)

```json
{
  "timestamp": 1700000000,
  "account": {
    "equity": 10500.00,
    "balance": 10000.00,
    "margin": 450.00,
    "free_margin": 10050.00,
    "floating_pl": 500.00
  },
  "bars": {
    "M5":  { "open": 1950.1, "high": 1951.2, "low": 1949.8, "close": 1950.9 },
    "M15": { "open": 1948.5, "high": 1951.5, "low": 1948.0, "close": 1950.9 },
    "M30": { "open": 1947.0, "high": 1952.0, "low": 1946.5, "close": 1950.9 },
    "H1":  { "open": 1945.0, "high": 1953.0, "low": 1944.5, "close": 1950.9 },
    "H4":  { "open": 1940.0, "high": 1955.0, "low": 1939.0, "close": 1950.9 },
    "D":   { "open": 1930.0, "high": 1960.0, "low": 1928.0, "close": 1950.9 },
    "W1":  { "open": 1920.0, "high": 1965.0, "low": 1918.0, "close": 1950.9 }
  }
}
```

---

## Database Schema

### `trades`
Stores every order event from MT5 — both real and paper trades.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | primary key |
| `ticket` | BIGINT | MT5 order ticket |
| `symbol` | VARCHAR | e.g. XAUUSD |
| `direction` | ENUM | buy, sell |
| `order_type` | ENUM | market, buy_limit, sell_limit, buy_stop, sell_stop, buy_stop_limit, sell_stop_limit |
| `order_state` | ENUM | pending, filled, cancelled, expired |
| `pending_price` | DECIMAL | trigger price for pending orders |
| `open_time` | TIMESTAMPTZ | when order was placed |
| `fill_time` | TIMESTAMPTZ | when pending order was filled |
| `close_time` | TIMESTAMPTZ | when position was closed |
| `open_price` | DECIMAL | fill price |
| `close_price` | DECIMAL | exit price |
| `volume` | DECIMAL | lot size |
| `tp` | DECIMAL | take profit level |
| `sl` | DECIMAL | stop loss level (may be null) |
| `profit` | DECIMAL | realized P&L |
| `swap` | DECIMAL | overnight swap |
| `commission` | DECIMAL | broker commission |
| `is_paper` | BOOLEAN | true = paper trade |
| `paper_mode` | ENUM | null, mirror, independent |

### `price_bars`
TimescaleDB hypertable for all OHLCV data.

| Column | Type |
|--------|------|
| `time` | TIMESTAMPTZ (partition key) |
| `symbol` | VARCHAR |
| `timeframe` | ENUM (M5, M15, M30, H1, H4, D, W1) |
| `open` / `high` / `low` / `close` | DECIMAL |
| `volume` | DECIMAL |

### `account_snapshots`
Point-in-time account state, sent every minute.

| Column | Type |
|--------|------|
| `timestamp` | TIMESTAMPTZ |
| `equity` | DECIMAL |
| `balance` | DECIMAL |
| `margin` | DECIMAL |
| `free_margin` | DECIMAL |
| `floating_pl` | DECIMAL |

### `insights`
Auto-generated findings from Insight Engine.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | |
| `type` | VARCHAR | e.g. time_bias, tf_confluence, loss_pattern |
| `description` | TEXT | human-readable finding |
| `confidence` | FLOAT | 0.0–1.0, based on sample size |
| `sample_size` | INT | number of trades supporting this insight |
| `discovered_at` | TIMESTAMPTZ | |
| `is_active` | BOOLEAN | false = superseded by newer insight |
| `data` | JSONB | raw stats supporting the finding |

### `alerts`
Record of every triggered warning.

| Column | Type |
|--------|------|
| `id` | UUID |
| `type` | VARCHAR |
| `message` | TEXT |
| `trigger_data` | JSONB |
| `sent_at` | TIMESTAMPTZ |
| `acknowledged` | BOOLEAN |

---

## Insight Engine

Runs as a background job after every new trade event. Analyzes the full trade history (wins and losses) to surface patterns automatically. No manual rule configuration required.

### Insight Categories

**From losing trades:**
- Time-of-day loss clusters (e.g., "74% of losses after 21:00")
- Counter-trend entries (H4 bearish + user bought → avg loss 3.1x avg win)
- Double-down amplification (second entry on losing position → outcome distribution)
- Wick-stop pattern (position stopped then reversed within 30 min)
- Hold-too-long pattern (would have broken even if held 30 min longer)

**From winning trades:**
- TF confluence patterns (H4 bullish + H1 pullback → win rate X%)
- Session win rates (London open vs NY open vs Asian)
- Pending vs market order win rate comparison
- Optimal exit timing (TP hit % by holding duration)

**Cross-analysis:**
- Paper vs real P&L divergence over time
- Which deviations from pattern correlate with losses

### Confidence Threshold
Insights are only surfaced when `sample_size >= 10` and `confidence >= 0.6` to avoid false patterns from small samples.

---

## Mirror Paper Trader

Runs in parallel with real trading. Learns from all trade history — wins and losses.

**Behavior:**
1. User opens a real order → system paper-enters at the same price simultaneously
2. Real trade: user manages freely (no hard SL, may double down)
3. Paper trade: system applies exit rules derived from winning trade patterns in history
4. Both run until closed
5. Dashboard shows Real P&L vs Paper P&L side-by-side
6. After paper trade closes → Insight Engine recalculates with new data point

**Paper exit logic (Phase 1):**
- Exit at statistical TP level learned from winning trades of same setup type
- Cut loss if price moves X points against (where X = median loss point in similar losing trades)
- Override: always close if floating loss exceeds equity buffer threshold

---

## Real-Time Alert Conditions (Phase 1, in-app only)

| Alert | Trigger |
|-------|---------|
| Equity Buffer Warning | Free margin would be exhausted if price moves < 10,000 points against all positions |
| Double-Down Warning | User opens same-direction order while existing position is in floating loss |
| Consecutive Loss | 3+ consecutive closed losses → suggest pause |
| Counter-Trend Entry | New order direction conflicts with H4 bias at time of entry |
| Pattern Alert | Engulfing or pin bar detected on M15/M30 matching historical entry conditions |

---

## React Dashboard

**Pages:**
1. **Live** — current price, trend bias per TF (W1→M5), open positions, equity buffer gauge, active alerts
2. **History** — trade log table with filters, P&L chart over time
3. **Paper vs Real** — side-by-side cumulative P&L comparison
4. **Insights** — cards showing auto-discovered patterns, confidence score, sample size
5. **Patterns** — real-time pattern detection status per timeframe

---

## Docker Compose Services

```yaml
services:
  db:       PostgreSQL 16 + TimescaleDB
  api:      Python FastAPI (port 8000)
  frontend: React + Vite (port 3000)
```

MT5 EA communicates with `api` via `http://localhost:8000`. All services on same Docker network. Data persisted via named volume on host.

---

## Out of Scope (Phase 1)

- Telegram notifications (Phase 2)
- Independent paper trader making its own entry decisions (Phase 2)
- ML-based pattern learning (Phase 2)
- Real EA execution (Phase 3)
- Multi-symbol support (XAUUSD only for now)

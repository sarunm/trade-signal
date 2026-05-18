# Trade Signal Partner — Phase 3: React Dashboard Design

## Goal

Build a single-page React dashboard that displays account info, alerts, insights, and paper vs real trade comparisons in near-realtime (polling every 30 seconds). Also add two new backend capabilities: a PatternDetector service that fires alerts for Pin Bar and Engulfing candle patterns on H1/H4, and a `pattern_win_rate` insight type that correlates historical patterns with trade outcomes.

---

## Architecture

### Frontend

- **Framework:** React 18 + Vite
- **Styling:** TailwindCSS
- **Port:** 3000 (Docker service)
- **Polling:** `setInterval` every 30 seconds, fetches all endpoints in parallel
- **State:** React `useState` + `useEffect` only — no external state library
- **Deployment:** Vite dev server in development; nginx serving built files in production (same Docker image, `npm run build` at container start)

### Backend additions

- CORS middleware on FastAPI allowing `http://localhost:3000`
- Two new endpoints: `GET /api/account`, `GET /api/trades`
- PatternDetector service wired into `price_tick` router
- `pattern_win_rate` computation added to `insight_engine.py`

### Docker

Add `frontend` service to `docker-compose.yml`:
- Build from `frontend/` directory
- Port mapping: `3000:3000`
- Depends on `api`

---

## Dashboard Layout

Single scrollable page, no tabs, no routing.

```
┌─────────────────────────────────────────────────────────┐
│  ACCOUNT BAR                                            │
│  Equity | Balance | Free Margin | Float P/L | Updated   │
├──────────────────────────┬──────────────────────────────┤
│  ALERTS                  │  INSIGHTS                    │
│  (unacknowledged first)  │  (sorted by confidence desc) │
│  type | message | [Ack]  │  type | description | conf%  │
├──────────────────────────┴──────────────────────────────┤
│  OPEN POSITIONS                                         │
│  ticket | dir | real entry | paper entry | paper SL/TP  │
├─────────────────────────────────────────────────────────┤
│  RECENT CLOSED TRADES (last 20)                         │
│  ticket | dir | real result | paper result | difference  │
└─────────────────────────────────────────────────────────┘
```

### Account Bar

- Fetches from `GET /api/account`
- Fields: `equity`, `balance`, `free_margin`, `floating_pl`, `timestamp`
- Shows "Last updated: X seconds ago" with a stale indicator if last fetch failed

### Alerts Panel

- Fetches from `GET /api/alerts` (all alerts, both acknowledged and not)
- Unacknowledged alerts shown first, red badge with count
- Each alert: type pill badge, message text, Acknowledge button
- Acknowledge calls `PATCH /api/alerts/{id}/acknowledge` immediately (does not wait for poll cycle)
- Acknowledged alerts shown below in muted/grey style

### Insights Panel

- Fetches from `GET /api/insights` (active only)
- Sorted by confidence descending
- Each insight: type pill badge (time_bias / session_bias / pattern_win_rate), description, confidence %, sample size in small text

### Open Positions

- Fetches from `GET /api/trades?state=open`
- Groups by ticket: real trade row paired with its mirror paper trade row
- Columns: ticket, direction, real entry price, paper entry price, paper SL, paper TP, real floating P/L

### Recent Closed Trades

- Fetches from `GET /api/trades?state=closed&limit=20`
- Groups by ticket: real + paper side by side
- Columns: ticket, direction, real profit/loss, paper profit/loss (simulated), difference
- Positive difference (paper > real) highlighted green, negative highlighted red

---

## New API Endpoints

### GET /api/account

Returns the most recent row from `account_snapshots`.

**Response:**
```json
{
  "equity": 10250.50,
  "balance": 10000.00,
  "margin": 150.00,
  "free_margin": 10100.50,
  "floating_pl": 250.50,
  "timestamp": "2026-05-18T10:30:00Z"
}
```

**Error:** 404 if no snapshot exists yet.

### GET /api/trades

Returns trades from the `trades` table.

**Query params:**
- `state`: `open` (close_price IS NULL) or `closed` (close_price IS NOT NULL). Default: `open`.
- `limit`: integer, default 50, max 200. Only applied when `state=closed`.
- `is_paper`: if omitted, returns both real and paper trades so the frontend can pair them.

**Response:** Array of trade objects:
```json
[
  {
    "id": "uuid",
    "ticket": 12345,
    "symbol": "XAUUSD",
    "direction": "buy",
    "order_type": "market",
    "order_state": "filled",
    "is_paper": false,
    "paper_mode": null,
    "open_price": "1920.50000",
    "close_price": null,
    "tp": "1940.00000",
    "sl": "1910.00000",
    "volume": 0.10,
    "profit": null,
    "open_time": "2026-05-18T08:00:00Z",
    "close_time": null
    // profit and close_price are null for open trades
  }
]
```

---

## New Backend Services

### PatternDetector (`api/services/pattern_detector.py`)

Called from `price_tick` router after `save_price_tick`. Checks H1 and H4 bars.

**Detection logic:**

**Pin Bar:**
- `body = abs(close - open)`
- `candle_range = high - low`
- `upper_wick = high - max(open, close)`
- `lower_wick = min(open, close) - low`
- Bullish pin: `lower_wick >= 2 * body` AND `lower_wick >= 0.6 * candle_range`
- Bearish pin: `upper_wick >= 2 * body` AND `upper_wick >= 0.6 * candle_range`

**Engulfing:**
- Reads last 2 bars
- Bullish engulfing: current close > prev open AND current open < prev close AND prev close < prev open (prev was bearish)
- Bearish engulfing: current close < prev open AND current open > prev close AND prev close > prev open (prev was bullish)

**Timeframes checked:** H1 and H4 only.

**Deduplication:** Do not create a new Alert if an alert of the same `type=pattern_alert` with the same pattern+timeframe exists with `sent_at` within the last 4 hours.

**Alert format:**
- `type`: `"pattern_alert"`
- `message`: `"Pin Bar (bullish) detected on H1"` or `"Engulfing (bearish) detected on H4"`
- `trigger_data`: `{"pattern": "pin_bar", "direction": "bullish", "timeframe": "H1", "open": ..., "high": ..., "low": ..., "close": ...}`

### pattern_win_rate Insight (`api/services/insight_engine.py`)

Added as a new compute function inside `insight_engine.py`, called from `run_insight_engine`.

**Logic:**
1. Query all closed real trades with `open_time IS NOT NULL`
2. For each trade, look up the H1 bar that matches `open_time` (within ±1 bar = ±1 hour)
3. Compute whether that bar matches a Pin Bar or Engulfing pattern using the same detection logic
4. Group by pattern type, compute win rate (profit > 0)
5. If sample ≥ 10 and win_rate ≥ 0.6: upsert a `pattern_win_rate` insight
6. Deactivate old `pattern_win_rate` insights that no longer meet threshold

**Insight format:**
- `type`: `"pattern_win_rate"`
- `description`: `"Trades opened after a bullish Pin Bar on H1 have a 72% win rate (14 trades)"`
- `confidence`: win_rate as float
- `sample_size`: trade count
- `data`: `{"pattern": "pin_bar", "direction": "bullish", "timeframe": "H1", "win_rate": 0.72}`

---

## CORS

Add `CORSMiddleware` to `api/main.py`:
- Allow origins: `["http://localhost:3000"]`
- Allow methods: `["*"]`
- Allow headers: `["*"]`

---

## Polling & Error Handling

- All 5 fetches run in parallel via `Promise.all` every 30 seconds
- Each fetch result updates its own piece of state independently — one failing fetch does not block others
- If a fetch fails: show last known data with a warning badge "Data may be stale"
- Show "Last updated: Xs ago" timestamp on account bar, updates every second via a separate `setInterval`

---

## File Structure

**New files:**
```
api/
  routers/account.py         — GET /api/account
  routers/trades.py          — GET /api/trades
  services/pattern_detector.py

frontend/
  Dockerfile
  package.json
  vite.config.js
  tailwind.config.js
  index.html
  src/
    main.jsx
    App.jsx
    hooks/
      usePolling.js          — shared polling logic
    components/
      AccountBar.jsx
      AlertsPanel.jsx
      InsightsPanel.jsx
      OpenPositions.jsx
      ClosedTrades.jsx
```

**Modified files:**
```
api/
  main.py                    — add CORS, include account_router and trades_router
  routers/price_tick.py      — call pattern_detector after save_price_tick
  services/insight_engine.py — add _compute_pattern_win_rate
  schemas/account.py         — AccountResponse schema (new)
  schemas/trade.py           — TradeResponse schema (new)

docker-compose.yml           — add frontend service
```

---

## Out of Scope

- Authentication / login
- Real-time chart (user monitors in MT5)
- Mobile responsive layout (desktop-first only)
- WebSocket / server-sent events (polling is sufficient)
- Historical price chart in dashboard

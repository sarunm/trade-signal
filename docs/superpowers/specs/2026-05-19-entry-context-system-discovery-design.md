# Entry Context & Trading System Discovery — Design Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Maintain `implementation-notes.md`** throughout development: record every decision not in this spec, deviation from spec, trade-off chosen, and open question for review.

**Goal:** Capture rich market context at every trade entry (mostly automatic, 2-field manual tag) so the insight engine can statistically discover which conditions in the user's intuitive system correlate with winning trades — building labeled data for an eventual autonomous EA.

**Architecture:** New `entry_context` service auto-fills 5 fields on every ENTRY_IN event. User manually tags 2 fields via dashboard dropdowns (no submit — auto-save on change). Insight engine gains 5 new computation functions that group tagged trades and surface win-rate correlations. Two new alert types fire when a historically poor setup is detected. Dashboard gets tag dropdowns, 2-row closed-trade layout, Ack All, and paging.

**Tech Stack:** FastAPI + SQLAlchemy async + PostgreSQL + React + Tailwind (existing stack, no new deps)

---

## Phase Roadmap

```
Phase 1 (this spec): capture labeled data + statistical insight discovery
Phase 2 (separate spec): EA rules derived from discovered patterns
Phase 3 (separate spec): ML classifier trained on Phase 1 labeled data (needs 200+ trades)
```

---

## 1. Data Model

### 1.1 New columns on `trades` table (all nullable — no backfill required)

| Column | Type | Source | Description |
|---|---|---|---|
| `setup_pattern` | VARCHAR(30) | Manual tag | Chart pattern user identified at entry |
| `trade_bias` | VARCHAR(10) | Manual tag | User's directional conviction |
| `near_fib_level` | VARCHAR(10) | Auto on ENTRY_IN | Closest ROM Fib level label (e.g. `S0.235`, `PP`, `R1.000`) |
| `fib_distance_pts` | NUMERIC(8,2) | Auto on ENTRY_IN | Points between open_price and nearest Fib level |
| `entry_candle` | VARCHAR(30) | Auto on ENTRY_IN | Candle pattern found across TFs (e.g. `pin_bar_bullish`) |
| `entry_candle_tf` | VARCHAR(5) | Auto on ENTRY_IN | TF where pattern was detected (e.g. `H4`, `H1`, `M30`, `M15`) |
| `is_rescue` | BOOLEAN | Auto on ENTRY_IN | True if ≥1 open real trade in same symbol+direction exists |
| `post_close_run_pts` | NUMERIC(8,2) | Auto post-close | Max favorable move in 8h after close (H1 bars) |

**`setup_pattern` valid values:**
`double_top`, `double_bottom`, `triple_top`, `triple_bottom`, `rounded_top`, `rounded_bottom`, `price_cluster`, `other`, `null` (not tagged)

**`trade_bias` valid values:** `bullish`, `bearish`, `null` (not tagged)

**`entry_candle` valid values:** `pin_bar_bullish`, `pin_bar_bearish`, `engulfing_bullish`, `engulfing_bearish`, `doji`, `none`

**`entry_candle_tf` valid values:** `H4`, `H1`, `M30`, `M15`, `null` (when entry_candle is `none`)

### 1.2 Migration: `005_add_entry_context.py`

```python
# alembic/versions/005_add_entry_context.py
def upgrade():
    op.add_column("trades", sa.Column("setup_pattern", sa.String(30), nullable=True))
    op.add_column("trades", sa.Column("trade_bias", sa.String(10), nullable=True))
    op.add_column("trades", sa.Column("near_fib_level", sa.String(10), nullable=True))
    op.add_column("trades", sa.Column("fib_distance_pts", sa.Numeric(8, 2), nullable=True))
    op.add_column("trades", sa.Column("entry_candle", sa.String(30), nullable=True))
    op.add_column("trades", sa.Column("entry_candle_tf", sa.String(5), nullable=True))
    op.add_column("trades", sa.Column("is_rescue", sa.Boolean, nullable=True))
    op.add_column("trades", sa.Column("post_close_run_pts", sa.Numeric(8, 2), nullable=True))

def downgrade():
    for col in ["setup_pattern", "trade_bias", "near_fib_level",
                "fib_distance_pts", "entry_candle", "entry_candle_tf",
                "is_rescue", "post_close_run_pts"]:
        op.drop_column("trades", col)
```

---

## 2. Auto-Fill Entry Context

### 2.1 New file: `api/services/entry_context.py`

Called by `trade_logger.py` immediately after a real trade ENTRY_IN is saved.

```python
async def fill_entry_context(session: AsyncSession, trade: Trade) -> None:
    """Fills near_fib_level, fib_distance_pts, entry_candle, entry_candle_tf, is_rescue. No commit — caller commits."""
    await _fill_fib_proximity(session, trade)
    await _fill_entry_candle(session, trade)
    await _fill_is_rescue(session, trade)
```

#### `_fill_fib_proximity(session, trade)`

1. Query `fib_levels` table for `symbol = trade.symbol` (most recent row)
2. If no row → skip (fields stay null)
3. Collect all price values from `levels` dict + `extensions` dict (exclude `"0.000"` PP label — use its price but label it `"PP"`)
4. For each label/price pair, compute `abs(float(trade.open_price) - price)`
5. Find the minimum distance → set `trade.near_fib_level = label`, `trade.fib_distance_pts = distance`

Label mapping: keys from `levels` dict → prefix `R` (e.g. key `"0.235"` → label `"R0.235"`, `"1.618"` → `"R1.618"`), except `"0.000"` → `"PP"`. Keys from `extensions` dict → prefix `S` (e.g. `"0.235"` → `"S0.235"`, `"1.618"` → `"S1.618"`). Store the full label string, e.g. `"S0.235"`, `"R1.000"`, `"PP"` — not abbreviated.

#### `_fill_entry_candle(session, trade)`

Scans timeframes in priority order `[H4, H1, M30, M15]`. Uses the first TF where a recognisable pattern is found.

For each TF in priority order:
1. If `trade.open_time` is None → skip all
2. Compute `bar_start = trade.open_time` floored to the TF period (e.g. H4 → floor to 4-hour boundary)
3. Query current bar: `symbol = trade.symbol AND timeframe = TF AND time >= bar_start AND time < bar_start + TF_duration`
4. Query previous bar: immediately preceding the current bar
5. If no current bar for this TF → try next TF
6. Build `bars = [prev_bar_dict, current_bar_dict]` (skip prev if not found)
7. Run `detect_pin_bar(bars)` → `"pin_bar_bullish"` / `"pin_bar_bearish"`
8. Else `detect_engulfing(bars)` → `"engulfing_bullish"` / `"engulfing_bearish"`
9. Else if `open == close` → `"doji"`
10. If pattern found (not doji counts as pattern only for pin/engulfing): set `trade.entry_candle = pattern`, `trade.entry_candle_tf = TF` → stop scanning

If no pattern found on any TF: `trade.entry_candle = "none"`, `trade.entry_candle_tf = null`

#### `_fill_is_rescue(session, trade)`

Query: `Trade` where `is_paper=False`, `symbol=trade.symbol`, `direction=trade.direction`, `order_state=filled`, `close_time IS NULL`, `ticket != trade.ticket`

`trade.is_rescue = count > 0`

### 2.2 Wire-up in `trade_logger.py`

After the trade ENTRY_IN upsert completes (only for `is_paper=False` and `open_price is not None`):

```python
from services.entry_context import fill_entry_context

# existing: session.add(trade); await session.flush()
if not event.is_paper and event.open_price is not None:
    await fill_entry_context(session, trade)
```

---

## 3. API Changes

### 3.1 New endpoint: `PATCH /api/trades/{ticket}/tag`

File: `api/routers/trades.py`

**Request body:**
```json
{ "setup_pattern": "double_bottom", "trade_bias": "bullish" }
```

Both fields optional (can tag just one). Validates `setup_pattern` against allowed values; rejects unknown values with 422.

**Behaviour:** Updates the real trade (`is_paper=False`) with `ticket = {ticket}`. Returns 404 if not found.

**Response:** Full `TradeResponse` of the updated trade.

### 3.2 New endpoint: `POST /api/alerts/acknowledge-all`

File: `api/routers/alerts.py`

Sets `acknowledged = True` on all alerts where `acknowledged = False`. Returns `{"acknowledged": N}` (count of rows updated).

### 3.3 Modified: `GET /api/trades`

Add `offset: int = Query(0, ge=0)` parameter. Apply `.offset(offset).limit(limit)` to both open and closed queries.

Include new columns in `TradeResponse` schema:
```python
setup_pattern: Optional[str]
trade_bias: Optional[str]
near_fib_level: Optional[str]
fib_distance_pts: Optional[Decimal]
entry_candle: Optional[str]
entry_candle_tf: Optional[str]
is_rescue: Optional[bool]
post_close_run_pts: Optional[Decimal]
```

---

## 4. Insight Engine — 5 New Functions

File: `api/services/insight_engine.py`

Add to `run_insight_engine()`:
```python
tagged = [t for t in trades if t.setup_pattern is not None]
await _compute_setup_win_rate(session, tagged)
await _compute_fib_proximity_win_rate(session, tagged)
await _compute_rescue_outcome(session, trades)
await _compute_best_combo(session, tagged)
await _compute_post_close_run(session, trades, session)
```

`MIN_SAMPLE_SIZE = 5` for all new insight types (lower than existing 10 — fewer tagged trades expected initially).

### 4.1 `_compute_setup_win_rate(session, tagged)`

Group tagged real closed trades by `(setup_pattern, trade_bias, near_fib_level)`. For each group with `count >= 5`:
- `win_rate = wins / total`
- `avg_profit = mean(profit)`

Deactivate old `setup_win_rate` insights. Create one `Insight` per qualifying group:
```
type: "setup_win_rate"
description: "double_bottom + bullish + near S2 → ชนะ 78% (18 เทรด) เฉลี่ย +฿1,240"
confidence: win_rate
sample_size: total
data: {pattern, bias, fib_level, win_rate, avg_profit, trades: total}
```

### 4.2 `_compute_fib_proximity_win_rate(session, tagged)`

Bucket `fib_distance_pts` into three groups:
- `close`: fib_distance_pts < 5
- `medium`: 5 ≤ fib_distance_pts < 15
- `far`: fib_distance_pts ≥ 15

For each bucket with count ≥ 5, compute win_rate. Only create insight if any two buckets differ by ≥ 20 percentage points (otherwise not actionable).

```
type: "fib_proximity_win_rate"
description: "Entry ห่าง Fib < 5 pts → 74% | 5-15 pts → 51% | >15 pts → 38% (N เทรด)"
```

### 4.3 `_compute_rescue_outcome(session, trades)`

Split trades into `is_rescue=True` and `is_rescue=False` (both groups ≥ 5 needed).

```
type: "rescue_outcome"
description: "ไม้แก้: ชนะ 45% (20 เทรด) vs ไม้เดิม: ชนะ 68% (40 เทรด)"
data: {rescue_win_rate, initial_win_rate, rescue_count, initial_count}
```

### 4.4 `_compute_best_combo(session, tagged)`

Same grouping as setup_win_rate but include `session` dimension. Derive session from `open_time` converted to ICT (UTC+7) using `_assign_session()` helper — pass the ICT hour, not UTC hour, so morning/afternoon sessions align with user's actual trading day. Report top 3 combinations by win_rate (min 5 trades each).

```
type: "best_combo"
description: "Best: morning + double_bottom + bullish + near S2 → 83% win rate (12 เทรด)"
data: {combos: [{pattern, bias, fib_level, session, win_rate, avg_profit, count}, ...]}
```

### 4.5 `_compute_post_close_run(session, trades)`

**Step 1 — Backfill `post_close_run_pts` for closed real trades where it's null:**

For each real closed trade with `close_price IS NOT NULL AND post_close_run_pts IS NULL`:
- Query H1 bars: `symbol = trade.symbol, timeframe = H1, time >= close_time, time <= close_time + 8h`
- If no bars → skip
- BUY: `run = max(high) - close_price`; SELL: `run = close_price - min(low)`
- If `run > 0`: `trade.post_close_run_pts = run`

**Step 2 — Compute insight from tagged winning trades with post_close_run_pts filled:**
(Both steps run inside one function. Backfill first, then compute insight on the now-complete data.)

Group winning tagged trades by `setup_pattern`. For each pattern with ≥ 3 trades:

```
type: "post_close_run"
description: "double_bottom → ราคาวิ่งต่อได้เฉลี่ย 420 pts หลังคุณปิด | price_cluster → 185 pts"
data: {by_pattern: {pattern: avg_run_pts, ...}, overall_avg: N}
```

---

## 5. New Alert Types

File: `api/services/alert_manager.py`

Called from `run_insight_engine()` after the 5 insight functions:

```python
await _check_low_winrate_setup(session, tagged)
await _check_rescue_ineffective(session, trades)
```

Cooldown: 24 hours per alert type (check `Alert.sent_at > now - 24h` before inserting).

### 5.1 `_check_low_winrate_setup`

For each `(setup_pattern, trade_bias)` combination used ≥ 5 times total with `win_rate < 0.40`:

```
type: "low_winrate_setup"
message: "double_top + bullish: ชนะแค่ 28% (9 เทรด) — setup นี้ประวัติไม่ดี พิจารณาใหม่"
trigger_data: {pattern, bias, win_rate, count}
```

### 5.2 `_check_rescue_ineffective`

If rescue trade win_rate < 0.35 AND rescue count ≥ 5 AND (initial_win_rate - rescue_win_rate) > 0.20:

```
type: "rescue_ineffective"
message: "ไม้แก้ชนะแค่ 30% vs ไม้เดิม 65% — ข้อมูลบอกว่าตัดขาดทุนแล้วเริ่มใหม่ดีกว่า"
trigger_data: {rescue_win_rate, initial_win_rate, rescue_count}
```

---

## 6. Frontend Changes

### 6.1 Tag dropdowns in Open Positions table

File: `frontend/src/components/OpenPositionsPanel.jsx` (modify existing)

For each row where `is_paper = false` and `order_state = "filled"`:

Add after profit column:
```jsx
<SetupTag ticket={trade.ticket} currentPattern={trade.setup_pattern} currentBias={trade.trade_bias} />
```

`SetupTag` component:
- Two `<select>` elements, no submit button
- `onChange` → `PATCH /api/trades/{ticket}/tag` with `{setup_pattern, trade_bias}`
- On success: update local state
- Pattern options: `—`, `Double Bottom`, `Double Top`, `Triple Bottom`, `Triple Top`, `Rounded Bottom`, `Rounded Top`, `Price Cluster`, `Other`
- Bias options: `—`, `Bullish`, `Bearish`
- Values sent to API: lowercase with underscores (e.g. `double_bottom`)
- Also display read-only: `near_fib_level` (e.g. `near S2`) and `h1_candle` (e.g. `pin_bar_bullish`) as small grey text

### 6.2 Closed Trades 2-row layout

File: `frontend/src/components/ClosedTradesPanel.jsx` (modify existing)

Group closed trades by `ticket`. For each ticket, find the real trade and its paper counterpart (same ticket, `is_paper=true`).

Render as a card:
```
┌──────────────────────────────────────────────────────────┐
│ #12345  BUY                                              │
│ Real : entry 4,870.00  exit 4,890.00  +฿1,200          │
│ Paper: entry 4,870.00  exit 4,920.00  +฿1,800  Δ+฿600  │
└──────────────────────────────────────────────────────────┘
```

- If no paper trade for a ticket: single row, no paper line
- `Δ = paper_profit - real_profit` (positive = user closed early, leaving profit)
- `Δ` coloured green if positive, red if negative

### 6.3 Ack All button

File: `frontend/src/components/AlertsPanel.jsx` (modify existing)

Add `[Ack All]` button in header row of alerts section. On click: `POST /api/alerts/acknowledge-all` → on success, refresh alerts list.

### 6.4 Paging on Open Positions + Closed Trades

Both panels get a paging control:

```jsx
<select onChange={setLimit} value={limit}>
  <option value={10}>10</option>
  <option value={20}>20</option>
  <option value={50}>50</option>
  <option value={100}>100</option>
</select>
```

- Default: 20
- Fetch: `GET /api/trades?state=open&limit={limit}&offset={offset}`
- Show prev/next buttons when `result.length === limit` (next) or `offset > 0` (prev)

---

## 7. Testing Strategy

### 7.1 `tests/test_entry_context.py` (new file)

- `test_fill_fib_proximity_finds_nearest_level` — trade open_price near S2, verify near_fib_level=S2
- `test_fill_fib_proximity_skips_when_no_fib_data` — no fib_levels row, fields stay null
- `test_fill_entry_candle_detects_pin_bar_on_h4` — H4 bar is bullish pin bar → entry_candle="pin_bar_bullish", entry_candle_tf="H4"
- `test_fill_entry_candle_falls_back_to_h1_when_no_h4` — no H4 bar, H1 has engulfing → entry_candle_tf="H1"
- `test_fill_entry_candle_returns_none_when_no_pattern_any_tf` — no pattern on any TF → entry_candle="none", entry_candle_tf=null
- `test_fill_is_rescue_true_when_same_direction_open` — existing open buy, new buy entry → is_rescue=True
- `test_fill_is_rescue_false_when_no_existing` — no open trades → is_rescue=False
- `test_entry_context_auto_filled_on_trade_event` — POST /api/trade-events ENTRY_IN, check near_fib_level is set

### 7.2 `tests/test_insight_engine.py` (add)

- `test_setup_win_rate_insight_created` — 5+ tagged trades, verify insight with correct win_rate
- `test_fib_proximity_win_rate_insight_created` — trades in close/medium/far buckets
- `test_rescue_outcome_insight_created` — mix of is_rescue true/false trades
- `test_best_combo_insight_created` — tagged trades across multiple sessions
- `test_post_close_run_backfills_trade` — H1 bars after close, verify post_close_run_pts set
- `test_post_close_run_insight_created` — winning tagged trades with post_close_run_pts filled

### 7.3 `tests/test_alert_manager.py` (add)

- `test_low_winrate_setup_alert_fires` — 5 double_top+bullish trades all losses → alert
- `test_low_winrate_setup_no_alert_when_good_winrate` — 70% win rate → no alert
- `test_rescue_ineffective_alert_fires` — rescue win_rate=30%, initial=70% → alert
- `test_rescue_ineffective_cooldown_deduplicates` — fires only once in 24h

### 7.4 `tests/test_trades_api.py` (add)

- `test_patch_tag_updates_setup_pattern` — PATCH /api/trades/{ticket}/tag → 200, fields updated
- `test_patch_tag_rejects_invalid_pattern` — unknown pattern value → 422
- `test_patch_tag_returns_404_for_unknown_ticket` — unknown ticket → 404
- `test_list_trades_respects_offset` — offset=10, verify first result skipped

### 7.5 `tests/test_alerts_api.py` (add)

- `test_acknowledge_all_marks_all_unacked` — POST /api/alerts/acknowledge-all → all acked

---

## 8. File Summary

| Action | File |
|---|---|
| Create | `api/services/entry_context.py` |
| Create | `api/alembic/versions/005_add_entry_context.py` |
| Create | `tests/test_entry_context.py` |
| Modify | `api/models/trade.py` — 8 new columns |
| Modify | `api/schemas/trade.py` — 8 new optional fields in TradeResponse |
| Modify | `api/services/trade_logger.py` — call fill_entry_context on ENTRY_IN |
| Modify | `api/services/insight_engine.py` — 5 new functions + call them |
| Modify | `api/services/alert_manager.py` — 2 new alert checks |
| Modify | `api/routers/trades.py` — PATCH tag endpoint + offset param |
| Modify | `api/routers/alerts.py` — POST acknowledge-all endpoint |
| Modify | `frontend/src/components/OpenPositionsPanel.jsx` — tag dropdowns |
| Modify | `frontend/src/components/ClosedTradesPanel.jsx` — 2-row layout + paging |
| Modify | `frontend/src/components/AlertsPanel.jsx` — Ack All button |

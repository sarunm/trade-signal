# Task Backlog

**Owner:** Claude adds tasks. Codex picks from the top.

**Workflow:**
1. Codex takes the top task → updates `.agents/active.md` (owner + status `in_progress`)
2. Implements per acceptance criteria
3. Runs verify commands — all must pass
4. Updates `.agents/handoff.md` → marks task done (~~strikethrough~~ or delete)

**Claude review:** After Codex marks done, Claude runs the review checklist in `AGENTS.md` before closing the task.

---

## Task Format

```
### TASK: <title>

**Why:** one line — what problem this solves
**Files to touch:**
- list of files to read/create/modify
**Acceptance criteria:**
- [ ] specific, testable, literal outcome
**Verify:**
exact commands to confirm it works
```

---

## Queue

### TASK: Commit pending changes (early-exit insight + ClosedTrades columns + EA position-ticket fix + AGENTS.md rewrite)

**Why:** Several changes were made in the current session but not committed: early_exit_rate insight, ClosedTrades entry/exit price columns, InsightsPanel amber color, EA DEAL_POSITION_ID fix for ENTRY_OUT deals, and AGENTS.md rewrite.
**Files to touch:**
- `api/services/insight_engine.py` (verify `_compute_early_exit_rate` exists)
- `frontend/src/components/ClosedTrades.jsx` (verify Entry + Exit Price columns)
- `frontend/src/components/InsightsPanel.jsx` (verify `early_exit_rate` amber color)
- `ea/TradeSignalBridge.mq5` (verify DEAL_POSITION_ID used for ENTRY_OUT in both SyncHistoryDeals and OnTradeTransaction)
- `AGENTS.md`
- `.agents/backlog.md`
- `.agents/active.md`
- `.agents/handoff.md`
**Acceptance criteria:**
- [ ] `pytest tests/ -v` passes (64 passed, 1 warning — no regressions)
- [ ] `cd frontend && npm run build` passes
- [ ] All changed files are staged and committed with a clear message
- [ ] `git log --oneline -1` shows the commit
**Verify:**
```bash
pytest tests/ -v
cd frontend && npm run build
git diff --stat HEAD
git log --oneline -3
```

---

### TASK: Fix Pydantic v2 deprecation warning

**Why:** `pytest tests/ -v` prints a `PydanticDeprecatedSince20` warning about class-based `Config`. Clean test output makes regressions easier to spot.
**Files to touch:**
- All files under `api/schemas/` and `api/models/` that use `class Config:`
- Run `grep -rn "class Config" api/` to find them
**Acceptance criteria:**
- [ ] `pytest tests/ -v` passes with **0 warnings** (not just 0 failures)
- [ ] No `class Config:` remains in `api/schemas/` or `api/models/`
- [ ] All replaced with `model_config = ConfigDict(...)` from `pydantic import ConfigDict`
- [ ] No existing schema or model behaviour changes — all 64 tests still pass
**Verify:**
```bash
grep -rn "class Config" api/
pytest tests/ -v 2>&1 | grep -E "warning|Warning|passed|failed"
```

---

### TASK: Add session-loss-streak alert

**Why:** `consecutive_loss` fires on any 3 losses in a row. A more useful alert is when those losses cluster in the same trading session (London / NY / Asia) — it tells the user to stop trading that session today.
**Files to touch:**
- `api/services/alert_manager.py` — add `_check_session_loss_streak`
- `api/models/alert.py` — verify no schema change needed (type is a free string)
- `tests/test_alert_manager.py` — add tests for the new alert
**Acceptance criteria:**
- [ ] New function `_check_session_loss_streak(session, event)` called from `check_trade_alerts`
- [ ] Alert type: `"session_loss_streak"`
- [ ] Fires when the last 3 closed real losses on the same symbol all fall in the same trading session (London 07-16 UTC, NY 13-22 UTC, Asia otherwise)
- [ ] Does NOT fire if the losses span different sessions
- [ ] `trigger_data` includes: `session`, `count`, `total_loss`, `tickets`
- [ ] At least 3 test cases: fires correctly, does not fire cross-session, does not fire with fewer than 3 losses
- [ ] `pytest tests/ -v` passes
**Verify:**
```bash
pytest tests/test_alert_manager.py -v
pytest tests/ -v
```

---

### TASK: Add cumulative P/L endpoint and sparkline to dashboard

**Why:** The dashboard shows per-trade P/L but not the trajectory over time. A sparkline of cumulative real P/L helps the user see if they are improving or declining.
**Files to touch:**
- `api/routers/trades.py` — add `GET /api/trades/pnl-history?days=30`
- `api/schemas/trade.py` — add `PnlHistoryPoint` response schema
- `tests/test_trades_api.py` — add tests for the new endpoint
- `frontend/src/components/PnlChart.jsx` — new component (Recharts `LineChart`)
- `frontend/src/App.jsx` — add `usePolling(fetchPnl)` and render `<PnlChart />`
**Acceptance criteria:**
- [ ] `GET /api/trades/pnl-history?days=30` returns JSON array of `[{date: "YYYY-MM-DD", cumulative_pnl: float}, ...]` sorted ascending by date
- [ ] Only includes closed real trades (`is_paper=false`, `close_time not null`, `profit not null`)
- [ ] `PnlChart` renders a Recharts `LineChart` — line is green when latest value > 0, red otherwise
- [ ] Chart is visible on the dashboard below ClosedTrades
- [ ] Empty state: "No closed trades yet" text (no chart crash)
- [ ] `pytest tests/ -v` passes
- [ ] `npm run build` passes
**Verify:**
```bash
pytest tests/test_trades_api.py -v
pytest tests/ -v
cd frontend && npm run build
curl "http://localhost:8000/api/trades/pnl-history?days=30"
```

---

### TASK: Fibonacci levels — EA compute + backend store + dashboard display

**Why:** User ดู fib levels จาก ROM indicator บน TradingView เพื่อหาแนวรับแนวต้าน ระบบควรคำนวณ fib เดียวกันและแสดงบน dashboard ได้เลยโดยไม่ต้องเปิด TradingView

**Design decisions (confirmed):**
- ใช้ D1 bars เท่านั้น (ROM แสดง levels เดิมทุก TF — fixed timeframe)
- Swing detection: pivot high/low จาก D1 bars ล่าสุด 60 candles, window = 5 bars
- Fib levels: 0.236, 0.382, 0.5, 0.618, 0.786
- Plot ทั้ง retracement (เหนือ 0.0) และ extension (ใต้ 0.0) เหมือน ROM
- ไม่มี alert ตอนนี้ — แค่แสดงข้อมูล

**Files to touch:**
- `ea/TradeSignalBridge.mq5` — เพิ่ม `ComputeFibLevels()` ใน `OnTimer()`, POST `/api/fib-levels`
- `api/alembic/versions/004_add_fib_levels.py` — migration ตาราง `fib_levels`
- `api/models/fib_level.py` — SQLAlchemy model
- `api/schemas/fib_level.py` — Pydantic schema สำหรับ POST และ GET
- `api/routers/fib_levels.py` — `POST /api/fib-levels`, `GET /api/fib-levels`
- `api/main.py` — register router
- `tests/test_fib_levels.py` — tests
- `frontend/src/components/FibPanel.jsx` — แสดง levels + highlight ระดับใกล้ price ปัจจุบัน
- `frontend/src/App.jsx` — เพิ่ม `usePolling(fetchFib)` และ render `<FibPanel />`

**DB schema (ตาราง `fib_levels`):**
```
id          — serial PK
symbol      — varchar (e.g. "GOLD")
timeframe   — varchar (e.g. "D1")
swing_high  — numeric
swing_low   — numeric
direction   — varchar ("bullish" | "bearish")  ← low ใหม่กว่า = bullish, high ใหม่กว่า = bearish
levels      — jsonb  ← {"0.236": 4670.14, "0.382": 4708.66, ...}
extensions  — jsonb  ← {"0.236": 4546.98, "0.382": 4508.46, ...}
computed_at — timestamptz
```
upsert by `(symbol, timeframe)` — เก็บแค่ชุดล่าสุด

**EA logic (`ComputeFibLevels` ใน MQL5):**
```
1. ดึง D1 bars 60 แท่งล่าสุด
2. หา pivot high: bar[i].high > bar[i-5..i+5].high ทุกตัว → เอาล่าสุด
3. หา pivot low:  bar[i].low  < bar[i-5..i+5].low  ทุกตัว → เอาล่าสุด
4. direction = pivot_high_time > pivot_low_time ? "bearish" : "bullish"
5. range = swing_high - swing_low
6. retracement levels (เหนือ swing_low): swing_low + range * [0.236, 0.382, 0.5, 0.618, 0.786]
7. extension levels (ใต้ swing_low):    swing_low - range * [0.236, 0.382, 0.5, 0.618, 0.786]
8. POST /api/fib-levels เป็น JSON
```

**FibPanel layout:**
```
┌─ Fibonacci (D1) ─────────────────────────────┐
│ Swing High: 4870.56   Swing Low: 4608.56      │
│ Direction: Bearish  │  Range: 262 pts         │
│                                               │
│ ▲ Retracement                                 │
│   0.786  4814.82  ░░░░░░░░░░░░░░░░░           │
│   0.618  4770.51  ░░░░░░░░░░░░                │  ← highlight ถ้า price ใกล้ ±0.5%
│   0.500  4739.58  ░░░░░░░░░░                  │
│   0.382  4708.66  ░░░░░░░░                    │
│   0.236  4670.14  ░░░░░░                      │
│ ── 0.000  4608.56 ─── (Swing Low) ───         │
│ ▼ Extension                                   │
│   0.236  4546.98                              │
│   0.382  4508.46                              │
│   0.500  4477.54                              │
└───────────────────────────────────────────────┘
```

**Acceptance criteria:**
- [ ] EA ส่ง `POST /api/fib-levels` ทุก `OnTimer()` cycle (ทุก 60s)
- [ ] Backend upsert ข้อมูลใน `fib_levels` table by `(symbol, timeframe)`
- [ ] `GET /api/fib-levels` คืน JSON ที่มี swing_high, swing_low, direction, levels, extensions
- [ ] FibPanel แสดง retracement levels เรียงจากสูงลงต่ำ และ extension levels ใต้ 0.0
- [ ] Level ที่ price ปัจจุบัน (bid จาก account หรือ last close) อยู่ใกล้ ±0.5% ของ range → highlight สีเหลือง
- [ ] ถ้า DB ไม่มีข้อมูล fib → แสดง "Waiting for EA data"
- [ ] `pytest tests/ -v` passes
- [ ] `npm run build` passes

**Verify:**
```bash
pytest tests/test_fib_levels.py -v
pytest tests/ -v
cd frontend && npm run build
curl http://localhost:8000/api/fib-levels
```

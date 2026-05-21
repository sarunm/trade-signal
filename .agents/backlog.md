# Task Backlog

**Roles:** Claude — design + assign + PR review + merge. Codex / agy — implement only.

**Workflow:**
1. Claude assigns `assignee` (codex|agy) and sets `status: pending` before dispatching
2. Agent picks **only** tasks where `assignee` matches their name
3. Agent creates branch: `git checkout -b <assignee>/<task-slug>` และ updates `status: in_progress`
4. Implements per acceptance criteria
5. Runs all verify commands — **all must pass before continuing**
6. Commits, opens PR to `main` via `gh pr create`
7. Updates `status: done` + writes `.agents/handoff.md` พร้อม PR URL
8. Claude reads `.agents/feedback.md` + reviews PR diff
9. Approved → Claude merges PR + pushes
10. Bugs found → Claude creates `[BUG]` task, requests changes on PR

**Branch naming:** `codex/<task-slug>` หรือ `agy/<task-slug>` เช่น `agy/fib-pp-weekly`

**Status values:** `pending` → `in_progress` → `done` | `blocked`

**Priority values:** `high` | `normal` | `low`

**"Fix later" rule:** ห้ามพูดว่า "แก้ทีหลัง" หรือ "เพิ่มทีหลัง" โดยไม่สร้าง task — ทุกครั้งที่ review เจอ deferred item ให้สร้าง task ทันทีพร้อม `priority: low` และ `remark:` อธิบายว่าทำไมถึง defer

**Bug rule:** Claude เจอ bug ระหว่าง review → สร้าง task ใหม่ prefix `[BUG]` พร้อม `blocks:` field ชี้ไปที่ task ต้นเหตุ อย่าแก้ inline

**Feedback rule:** Agent เจอ task แปลกๆ, scope ไม่ชัด, มีข้อแนะนำ, หรือ risk → เขียนใน `.agents/feedback.md` ก่อน open PR เสมอ

**Claude review:** Reads `.agents/feedback.md` → reviews PR → approves + merges หรือ requests changes

---

## Task Format

```
### TASK: <title>

**assignee:** codex | agy
**status:** pending | in_progress | done | blocked
**priority:** high | normal | low
**remark:** (optional) เหตุผลที่ defer หรือ context พิเศษ
**blocks:** (optional) task title ที่ task นี้ blocking อยู่

**Why:** one line — what problem this solves
**Files to touch:**
- list of files to read/create/modify
**Acceptance criteria:**
- [ ] specific, testable, literal outcome
**Verify:**
exact commands to confirm it works
```

## Bug Task Format

```
### TASK: [BUG] <title>

**assignee:** codex | agy
**status:** pending
**blocks:** <task title ที่พบ bug นี้ระหว่าง review>

**Why:** found during review of <commit/task>
**Root cause:** one line
**Files to touch:**
- specific files only
**Acceptance criteria:**
- [ ] specific fix verified
**Verify:**
exact commands
```

---

## Queue

### TASK: [BUG] Redesign Fib levels to match ROM indicator — PP method, Weekly period

**assignee:** agy
**status:** in_progress
**priority:** high
**remark:** agy implement ผิด method (swing detection) — ROM ใช้ PP = (H+L+C)/3 จาก previous week's OHLC

**Why:** Fib levels ที่แสดงบน dashboard ไม่ตรงกับ ROM indicator ใน TradingView เลย — ทำให้ใช้เป็น reference ไม่ได้
**Root cause:** agy implement swing detection แทน Fibonacci Pivot Point method

**ROM Formula (source: `docs/superpowers/specs/2026-05-21-rom-indicator-source.md`):**
```
period     = Week (previous completed week's OHLC)
PP         = (prev_high + prev_low + prev_close) / 3
range      = prev_high - prev_low
R1–R10     = PP + range * [0.235, 0.382, 0.5, 0.618, 0.728, 1.000, 1.235, 1.328, 1.5, 1.618]
S1–S10     = PP - range * [0.235, 0.382, 0.5, 0.618, 0.728, 1.000, 1.235, 1.328, 1.5, 1.618]
```

**Labels:** `PP`, `R1`–`R10` (resistance), `S1`–`S10` (support)

**Files to touch:**
- `ea/TradeSignalBridge.mq5` — rewrite `ComputeFibLevels()`: ใช้ `CopyRates(symbol, PERIOD_W1, 1, 1, rates)` แทน D1 swing detection
- `api/alembic/versions/` — new migration: drop `swing_high`/`swing_low`/`direction`, add `pp`/`prev_high`/`prev_low`/`prev_close`, rename `levels`→`resistance`, `extensions`→`support`
- `api/models/fib_level.py` — update columns
- `api/schemas/fib_level.py` — update fields + ratios (0.235–1.618, 10 levels)
- `api/routers/fib_levels.py` — update upsert logic
- `api/services/entry_context.py` — update `_fill_fib_proximity` label mapping (PP, R1–R10, S1–S10)
- `tests/test_fib_levels.py` — rewrite tests ให้ตรง PP method
- `frontend/src/components/FibPanel.jsx` — แสดง PP ตรงกลาง, R1–R10 เหนือ, S1–S10 ใต้ (ไม่มี swing high/low)

**DB schema ใหม่ (fib_levels):**
```
id           — serial PK
symbol       — varchar
period       — varchar ("W")
prev_high    — numeric
prev_low     — numeric
prev_close   — numeric
pp           — numeric
resistance   — jsonb  ← {"R1": 4715.0, "R2": ..., "R10": ...}
support      — jsonb  ← {"S1": 4685.0, "S2": ..., "S10": ...}
computed_at  — timestamptz
```
upsert by `(symbol, period)`

**EA logic:**
```
1. CopyRates(symbol, PERIOD_W1, 1, 1, rates) — previous completed week
2. PP    = (rates[0].high + rates[0].low + rates[0].close) / 3
3. range = rates[0].high - rates[0].low
4. R1–R10 = PP + range * [0.235, 0.382, 0.5, 0.618, 0.728, 1.000, 1.235, 1.328, 1.5, 1.618]
5. S1–S10 = PP - range * same ratios
6. POST /api/fib-levels — only when week changes (cache last week's bar time)
```

**FibPanel layout:**
```
┌─ Fibonacci (Weekly PP) ──────────────────────────┐
│ PP: 4700.00  │  Range: 262 pts  │  Week: prev    │
│                                                   │
│ ▲ Resistance                                      │
│   R10  1.618  4923.52                             │
│   ...                                             │
│   R1   0.235  4761.57  ← highlight ±5pts          │
│ ── PP  0.000  4700.00 ─────────────────────────── │
│ ▼ Support                                         │
│   S1   0.235  4638.43                             │
│   ...                                             │
│   S10  1.618  4476.48                             │
└───────────────────────────────────────────────────┘
```

**Acceptance criteria:**
- [ ] EA ใช้ `PERIOD_W1` bar ก่อนหน้า คำนวณ PP ถูกต้อง
- [ ] POST เฉพาะเมื่อ week เปลี่ยน (ไม่ยิงทุก 60s)
- [ ] `GET /api/fib-levels` คืน `pp`, `resistance` (R1–R10), `support` (S1–S10)
- [ ] FibPanel แสดง PP ตรงกลาง, R เหนือ, S ใต้
- [ ] `near_fib_level` ใน entry_context ใช้ labels ใหม่ (PP, R1, S3 ฯลฯ)
- [ ] `pytest tests/ -v` passes
- [ ] `npm run build` passes

**Verify:**
```bash
cd api && alembic upgrade head
cd api && pytest ../tests/test_fib_levels.py -v
cd api && pytest ../tests/ -v
cd frontend && npm run build
```

---

### TASK: [BUG] Fix P/L history anchor to use today instead of latest trade date

**assignee:** codex
**status:** done
**priority:** high
**blocks:** Add cumulative P/L endpoint and sparkline to dashboard

**Why:** `anchor_day` ใช้ date ของ trade ล่าสุดแทน today — ถ้าไม่มี trade ช่วงนี้ window จะ shift ไปอดีตโดยไม่แจ้ง user
**Root cause:** `api/routers/trades.py` line 83–84 ใช้ `max(close_time)` แทน `date.today()`
**Files to touch:**
- `api/routers/trades.py` — เปลี่ยน `anchor_day = max(...)` เป็น `anchor_day = datetime.now(timezone.utc).date()`
- `tests/test_trades_api.py` — เพิ่ม test case: trades เก่า 60 วัน ต้องไม่โผล่ใน `days=30`
**Acceptance criteria:**
- [ ] `GET /api/trades/pnl-history?days=30` ใช้ today เป็น anchor เสมอ
- [ ] Trade ที่เก่ากว่า 30 วันไม่ถูก return
- [ ] `pytest tests/ -v` passes
**Verify:**
```bash
cd api && pytest ../tests/test_trades_api.py -v
```

---

### TASK: Reduce EA fib POST frequency — skip when pivot unchanged

**assignee:** agy
**status:** done
**priority:** low
**remark:** ไม่ใช่ bug — upsert absorbs it แต่ยิง POST ทุก 60s ทั้งที่ D1 pivot เปลี่ยนแค่วันละครั้ง ทำให้ log รก

**Why:** `ComputeFibLevels()` ใน `OnTimer()` POST ทุก 60s แม้ข้อมูลไม่เปลี่ยน (~1440 POST/day สำหรับข้อมูลเดิม)
**Files to touch:**
- `ea/TradeSignalBridge.mq5` — cache `swing_high`/`swing_low` ของ POST ล่าสุด, skip ถ้าค่าเดิม
**Acceptance criteria:**
- [x] POST เกิดขึ้นเฉพาะเมื่อ pivot เปลี่ยน
- [x] ถ้า pivot ไม่เปลี่ยนตลอดวัน POST ไม่เกิน 2–3 ครั้ง
**Verify:**
Manual — ดู EA logs หลัง deploy

---

### TASK: Add cumulative P/L endpoint and sparkline to dashboard

**assignee:** codex
**status:** done

**Why:** The dashboard shows per-trade P/L but not the trajectory over time. A sparkline of cumulative real P/L helps the user see if they are improving or declining.
**Files to touch:**
- `api/routers/trades.py` — add `GET /api/trades/pnl-history?days=30`
- `api/schemas/trade.py` — add `PnlHistoryPoint` response schema
- `tests/test_trades_api.py` — add tests for the new endpoint
- `frontend/src/components/PnlChart.jsx` — new component (Recharts `LineChart`)
- `frontend/src/App.jsx` — add `usePolling(fetchPnl)` and render `<PnlChart />`
**Acceptance criteria:**
- [x] `GET /api/trades/pnl-history?days=30` returns JSON array of `[{date: "YYYY-MM-DD", cumulative_pnl: float}, ...]` sorted ascending by date
- [x] Only includes closed real trades (`is_paper=false`, `close_time not null`, `profit not null`)
- [x] `PnlChart` renders a Recharts `LineChart` — line is green when latest value > 0, red otherwise
- [x] Chart is visible on the dashboard below ClosedTrades
- [x] Empty state: "No closed trades yet" text (no chart crash)
- [x] `pytest tests/ -v` passes
- [x] `npm run build` passes
**Verify:**
```bash
pytest tests/test_trades_api.py -v
pytest tests/ -v
cd frontend && npm run build
curl "http://localhost:8000/api/trades/pnl-history?days=30"
```

---

### TASK: Fibonacci levels — EA compute + backend store + dashboard display

**assignee:** agy
**status:** done

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
- [x] EA ส่ง `POST /api/fib-levels` ทุก `OnTimer()` cycle (ทุก 60s)
- [x] Backend upsert ข้อมูลใน `fib_levels` table by `(symbol, timeframe)`
- [x] `GET /api/fib-levels` คืน JSON ที่มี swing_high, swing_low, direction, levels, extensions
- [x] FibPanel แสดง retracement levels เรียงจากสูงลงต่ำ และ extension levels ใต้ 0.0
- [x] Level ที่ price ปัจจุบัน (bid จาก account หรือ last close) อยู่ใกล้ ±0.5% ของ range → highlight สีเหลือง
- [x] ถ้า DB ไม่มีข้อมูล fib → แสดง "Waiting for EA data"
- [x] `pytest tests/ -v` passes
- [x] `npm run build` passes

**Verify:**
```bash
pytest tests/test_fib_levels.py -v
pytest tests/ -v
cd frontend && npm run build
curl http://localhost:8000/api/fib-levels
```

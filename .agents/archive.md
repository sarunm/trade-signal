# Task Archive

Tasks ที่ `status: done` — เก็บไว้เป็น reference

---

### TASK: [BUG] Fix undeclared g_last_market_tick_sent in EA

**assignee:** codex | **status:** done | **priority:** high
**commit:** 187649f fix: mark market tick throttle task done / b12897c fix: restore market tick throttle state

**Why:** found during review of commit 6fc99cb — EA will not compile
**Root cause:** `g_last_market_tick_sent` declaration was deleted from globals but usages at lines 458 + 502 remain

---

### TASK: [BUG] Fix fib_level model uses JSON instead of JSONB

**assignee:** codex | **status:** done | **priority:** low
**commit:** f9d0e3d fix: use JSONB for fib level payloads

**Why:** found during review of commit 6fc99cb — `api/models/fib_level.py` declares `resistance` + `support` เป็น `JSON` แต่ DB columns เป็น `JSONB` จาก migration 004
**Root cause:** Codex ใช้ `JSON` แทน `JSONB` ตอน redesign model

---

### TASK: [BUG] Redesign Fib levels to match ROM indicator — PP method, Weekly period

**assignee:** agy | **status:** done | **priority:** high
**remark:** agy implement ผิด method (swing detection) — ROM ใช้ PP = (H+L+C)/3 จาก previous week's OHLC
**commit:** 6fc99cb feat: redesign Fibonacci levels to match ROM PP method

**Why:** Fib levels ไม่ตรงกับ ROM indicator ใน TradingView
**Root cause:** agy implement swing detection แทน Fibonacci Pivot Point method

---

### TASK: [BUG] Fix P/L history anchor to use today instead of latest trade date

**assignee:** codex | **status:** done | **priority:** high
**blocks:** Add cumulative P/L endpoint and sparkline to dashboard

**Why:** `anchor_day` ใช้ date ของ trade ล่าสุดแทน today
**Root cause:** `api/routers/trades.py` ใช้ `max(close_time)` แทน `date.today()`

---

### TASK: Reduce EA fib POST frequency — skip when pivot unchanged

**assignee:** agy | **status:** done | **priority:** low
**remark:** ไม่ใช่ bug — upsert absorbs it แต่ยิง POST ทุก 60s ทำให้ log รก

**Why:** `ComputeFibLevels()` POST ทุก 60s แม้ข้อมูลไม่เปลี่ยน
**Fix:** cache `g_last_sent_week_time`, skip ถ้า week bar ไม่เปลี่ยน

---

### TASK: Add cumulative P/L endpoint and sparkline to dashboard

**assignee:** codex | **status:** done

**Why:** dashboard ไม่มี trajectory P&L over time
**Delivered:** `GET /api/trades/pnl-history?days=30` + `PnlChart.jsx` (Recharts LineChart)

---

### TASK: Fibonacci levels — EA compute + backend store + dashboard display

**assignee:** agy | **status:** done
**remark:** design เดิมใช้ swing detection D1 — superseded โดย ROM PP redesign

**Why:** original implementation ก่อนรู้ว่า ROM ใช้ PP method
**Note:** task นี้ถูก replace ทั้งหมดโดย `[BUG] Redesign Fib levels to match ROM indicator`

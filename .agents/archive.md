# Task Archive

Tasks ที่ `status: done` — เก็บไว้เป็น reference

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

# Trade Advisor — Design Spec

**Date:** 2026-05-21  
**Status:** approved  
**Scope:** Entry evaluation + recovery map + live zone alerts

---

## Overview

ระบบ Trade Advisor ช่วยตอบ 3 คำถามระหว่าง trade lifecycle:

1. **ควรเปิด order ตรงนี้มั้ย?** — entry score ที่ ORDER_PLACED
2. **ควรปิดที่ไหน / เพิ่มที่ไหน?** — recovery map ตาม fib levels
3. **ราคาถึง zone แล้ว** — notification real-time เมื่อ price เข้า zone

---

## Architecture

```
[ORDER_PLACED]        → compute_entry_score() + compute_recovery_plan()
                        → store in trades.entry_score / trades.recovery_plan (JSONB)

[OnTick → /api/market-tick ~1s]
                        → check open trades vs recovery_plan zones
                        → create alert if zone crossed (cooldown: 1 per zone per trade)

[Frontend polls /api/trade-advisor every 10s]
                        → renders TradeAdvisor panel
                        → polls /api/alerts?unread=true every 10s
                        → fires Browser Web Notification when new alert arrives
```

**ไม่ต้องการ WebSocket** — polling 10s เพียงพอสำหรับ weekly fib zone alerts  
**ไม่ต้องการ infrastructure ใหม่** — ใช้ alert system + polling pattern ที่มีอยู่แล้ว

---

## Section 1: Entry Scoring

เรียก `compute_entry_score(trade, session, db)` ทันทีเมื่อ `order_state = ORDER_PLACED`

### Signals

| Signal | Source | คะแนน |
|---|---|---|
| **Fib alignment** | `trade.near_fib_level` ± 5 pts | +25 (PP), +20 (R/S level), 0 (ไกล) |
| **Session win rate** | insight_engine — session ปัจจุบัน | +20 (>60%), 0 (40–60%), −15 (<40%) |
| **Entry pattern** | `trade.entry_candle_type` | +20 (pin bar / engulfing ตรงทิศทาง) |
| **Rescue placement** | `trade.is_rescue` + `near_fib_level` | +15 (ตรง fib ± 5 pts), −15 (ไม่ตรง) |
| **ATR state** | `price_bars` H/L/C — 20-bar ATR avg | +10 (ATR ≤ 1.5× avg), −10 (ATR > 1.5× avg) |
| **Session peak hours** | `datetime.utcnow()` | +10 (London 9–11am / NY 2–4pm UTC), −10 (Fri >17:00 / Mon <8:00 UTC) |
| **Consecutive setup losses** | trades grouped by setup (ดูด้านล่าง) | −15 ต่อ setup (max −30) |

**Max score:** 100 pts (25+20+20+15+10+10) — consecutive losses และ rescue ไม่ดีสามารถทำให้ติดลบได้

### Verdict

```
70–100  ✅  Good entry
40–69   ⚠️  Caution
< 40    ❌  High risk
```

### นิยาม "1 Setup"

Setup = กลุ่ม trades ที่มี `symbol` + `session` (Asian/London/NY) + `direction` เดียวกัน  
Setup loss/win = net P&L ของกลุ่มนั้นหลัง close ทั้งหมด  
นับเฉพาะ `is_paper = False` และ `order_state = CLOSED`

### DB Changes

เพิ่มใน `trades` table:
```
entry_score    integer         nullable  ← 0–100
entry_verdict  varchar(20)     nullable  ← "good" | "caution" | "high_risk"
```

---

## Section 2: Recovery Map

เรียก `compute_recovery_plan(trade, fib_levels)` พร้อมกับ entry scoring

### Logic

| Direction | TP zones | Add zones | Cut |
|---|---|---|---|
| BUY | R levels เหนือ entry (3 ใกล้สุด, ascending) | S levels ใต้ entry (3 ใกล้สุด, descending) | S4 breached |
| SELL | S levels ใต้ entry (3 ใกล้สุด, descending) | R levels เหนือ entry (3 ใกล้สุด, ascending) | R4 breached |

ถ้า entry อยู่ระหว่าง levels → เลือก levels ที่ใกล้ที่สุดในทิศทางนั้น  
ถ้า fib_levels ไม่มีข้อมูล → `recovery_plan = null` (แสดง "Waiting for fib data")

### Storage Format (JSONB)

```json
{
  "entry_price": 4700.00,
  "direction": "buy",
  "tp": [
    {"label": "R1", "price": 4714.15, "pts": 14.15},
    {"label": "R2", "price": 4730.62, "pts": 30.62},
    {"label": "R3", "price": 4757.85, "pts": 57.85}
  ],
  "add": [
    {"label": "S1", "price": 4638.43, "pts": -61.57},
    {"label": "S2", "price": 4576.86, "pts": -123.14},
    {"label": "S3", "price": 4530.00, "pts": -170.00}
  ],
  "cut": {"label": "S4", "price": 4484.57, "pts": -215.43}
}
```

### DB Changes

เพิ่มใน `trades` table:
```
recovery_plan  jsonb  nullable
```

Generate ครั้งเดียวตอน trade เปิด — fib levels เป็น weekly ไม่เปลี่ยนกลางสัปดาห์

---

## Section 3: Live Zone Monitoring

### Trigger

ทุก `POST /api/market-tick` → `check_advisor_zones(session, tick)`  
ดู trades ทุกตัวที่ `is_paper=False`, `order_state` ∈ {`OPEN`, `PLACED`}, `recovery_plan IS NOT NULL`

### Zone Check Logic

```python
for trade in open_trades:
    plan = trade.recovery_plan
    bid = tick.bid

    # TP zones (price moved in favor)
    for zone in plan["tp"]:
        if crossed(bid, zone["price"], trade.direction, side="tp"):
            create_alert("tp_zone_reached", trade, zone)

    # Add zones (price moved against)
    for zone in plan["add"]:
        if crossed(bid, zone["price"], trade.direction, side="add"):
            create_alert("add_zone_reached", trade, zone)

    # Cut zone
    if crossed(bid, plan["cut"]["price"], trade.direction, side="cut"):
        create_alert("cut_zone_reached", trade, plan["cut"])
```

**`crossed()` logic:**

| Trade | Zone | Condition |
|---|---|---|
| BUY | add zone (S level) | `bid <= zone.price` |
| BUY | TP zone (R level) | `bid >= zone.price` |
| BUY | cut zone (S4) | `bid <= cut.price` |
| SELL | add zone (R level) | `bid >= zone.price` |
| SELL | TP zone (S level) | `bid <= zone.price` |
| SELL | cut zone (R4) | `bid >= cut.price` |

### Alert Types ใหม่

| type | ข้อความ | severity |
|---|---|---|
| `tp_zone_reached` | "Price at R2 (4730) — TP2 reached" | info |
| `add_zone_reached` | "Price at S2 (4577) — Add zone 2 reached" | warning |
| `cut_zone_reached` | "⚠️ S4 breached (4485) — consider cutting" | critical |

**Cooldown:** 1 alert ต่อ `(trade_id, zone_label)` — reset เมื่อ trade ปิด  
**ใช้ `alerts` table เดิม** — เพิ่ม `trade_id` column (FK → trades) ถ้ายังไม่มี

---

## Section 4: Frontend

### TradeAdvisor.jsx

แสดงต่อ 1 open trade (ถ้ามีหลาย trade → tabs หรือ list)

```
┌─ Trade Advisor ────────────────────────────────┐
│ BUY @ 4700.00  │  Score: 75  ✅ Good entry     │
│ Fib: PP ✓  Session: 62% ✓  Pattern: pin bar ✓  │
│                                                 │
│ ▲ TP Targets                                    │
│   R3  4757.85  +57 pts                          │
│   R2  4730.62  +30 pts  ← recommended           │
│   R1  4714.15  +14 pts  ← nearest               │
│ ─── entry: PP 4700.00 ──────────────────────── │
│ ▼ Add Zones                                     │
│   S1  4638.43  −62 pts                          │
│   S2  4576.86  −123 pts                         │
│   S3  4530.00  −170 pts                         │
│                                                 │
│ ✂️  Cut if S4 breached: 4484.57  (−216 pts)    │
└─────────────────────────────────────────────────┘
```

Score breakdown แสดง signal icons ด้านบน (✓/✗ ต่อ signal)  
ถ้า `recovery_plan = null` → แสดง "Waiting for fib data"  
ถ้าไม่มี open trade → แสดง "No open trades"

### useTradeAlerts.js

```javascript
// polls /api/alerts?unread=true&types=tp_zone_reached,add_zone_reached,cut_zone_reached
// interval: 10s
// เมื่อพบ alert ใหม่ → new Notification(title, { body, icon })
// ต้อง request permission ครั้งแรก (Notification.requestPermission())
```

macOS notification ผ่าน Browser Web Notifications API — ใช้ได้เลยถ้า dashboard tab เปิดอยู่

### Endpoint ใหม่

`GET /api/trade-advisor` — คืน open trades พร้อม `entry_score`, `entry_verdict`, `recovery_plan`

---

## Files to Create / Modify

### New
- `api/services/trade_advisor.py` — `compute_entry_score()`, `compute_recovery_plan()`, `check_advisor_zones()`
- `api/routers/trade_advisor.py` — `GET /api/trade-advisor`
- `api/alembic/versions/008_add_trade_advisor_fields.py` — `entry_score`, `entry_verdict`, `recovery_plan` บน trades; `trade_id` FK บน alerts (ถ้าไม่มี)
- `frontend/src/components/TradeAdvisor.jsx`
- `frontend/src/hooks/useTradeAlerts.js`
- `tests/test_trade_advisor.py`

### Modified
- `api/routers/trade_events.py` — hook `compute_entry_score()` + `compute_recovery_plan()` เมื่อ `ORDER_PLACED`
- `api/routers/market_tick.py` — hook `check_advisor_zones()` ทุก tick
- `api/main.py` — register trade_advisor router
- `frontend/src/App.jsx` — เพิ่ม `<TradeAdvisor />` + `useTradeAlerts()`

---

## Testing

```bash
cd api && pytest ../tests/test_trade_advisor.py -v
cd api && pytest ../tests/ -v
cd frontend && npm run build
```

**Test cases ที่ต้องมี:**
- `test_entry_score_good_entry` — PP + good session + pattern → score ≥ 70
- `test_entry_score_high_risk` — ไม่มี fib + bad session + 2 setup losses → score ≤ 39
- `test_recovery_plan_buy` — BUY trade → TP = R levels, Add = S levels, Cut = S4
- `test_recovery_plan_sell` — SELL trade → TP = S levels, Add = R levels, Cut = R4
- `test_zone_check_add_alert` — price ผ่าน S1 → alert `add_zone_reached` ถูก create
- `test_zone_check_cooldown` — price ผ่าน S1 สองครั้ง → alert ถูก create แค่ 1 ครั้ง
- `test_zone_check_cut_alert` — price ผ่าน S4 → alert `cut_zone_reached`

---

## Open Questions

_ไม่มี — design confirmed ทั้งหมด_

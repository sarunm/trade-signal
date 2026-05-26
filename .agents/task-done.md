# Done Tasks

Archive of completed tasks moved out of `backlog.md`. Kept for audit/reference. Source of truth for what shipped is git history.

---

### TASK: Trader Profile MCP — Phase 1 implementation

**assignee:** codex
**status:** done
**priority:** normal
**remark:** spec + plan ครบแล้ว — `docs/superpowers/specs/2026-05-21-trader-profile-mcp-design.md` + `docs/superpowers/plans/2026-05-21-trader-profile-mcp.md`

**Why:** ระบบควรสามารถตอบคำถามเกี่ยวกับ trader profile ได้ผ่าน MCP tools — win rate, fib proximity, session performance ฯลฯ
**Files to touch:**
- ดูรายละเอียดใน `docs/superpowers/plans/2026-05-21-trader-profile-mcp.md`
**Acceptance criteria:**
- ดูใน plan file
**Verify:**
- ดูใน plan file

---

### TASK: Trade Advisor — entry scoring + recovery map + live zone alerts

**assignee:** agy
**status:** done
**priority:** normal
**remark:** spec ได้รับการอนุมัติแล้วที่ `docs/superpowers/specs/2026-05-21-trade-advisor-design.md` — completed in branch agy/trade-advisor

**Why:** ให้ระบบช่วย evaluate entry, แสดง recovery plan ตาม fib levels, และ alert เมื่อ price เข้า zone
**Files to touch:**
- `api/services/trade_advisor.py` (New)
- `api/routers/trade_advisor.py` (New)
- `api/alembic/versions/008_add_trade_advisor_fields.py` (New)
- `frontend/src/components/TradeAdvisor.jsx` (New)
- `frontend/src/hooks/useTradeAlerts.js` (New)
- `tests/test_trade_advisor.py` (New)
- `api/routers/trade_events.py` (Modify)
- `api/routers/market_tick.py` (Modify)
- `api/main.py` (Modify)
- `frontend/src/App.jsx` (Modify)
**Acceptance criteria:**
- [ ] `compute_entry_score()` คำนวณคะแนนตาม spec (Fib alignment, Session win rate, Entry pattern, Rescue placement, ATR state, Session peak hours, Setup losses)
- [ ] `compute_recovery_plan()` คำนวณ TP/Add/Cut zones ตาม weekly fib levels
- [ ] `check_advisor_zones()` ส่ง alert เมื่อราคาถึง zone บน `/api/market-tick` พร้อม cooldown 1 alert ต่อ zone/trade
- [ ] `GET /api/trade-advisor` คืนข้อมูล open trades พร้อม score + recovery plan
- [ ] Frontend `TradeAdvisor.jsx` แสดงผล score breakdown + Targets/Zones/Cut
- [ ] `useTradeAlerts.js` ค้นหา alerts และแจ้งเตือนผ่าน Browser Web Notifications API ทุก 10 วินาที
- [ ] `pytest tests/test_trade_advisor.py -v` และชุดทดสอบทั้งหมดผ่านการทดสอบ
**Verify:**
```bash
cd api && pytest ../tests/test_trade_advisor.py -v
cd api && pytest ../tests/ -v
cd frontend && npm run build
```

---

### TASK: Indicator Engine Infrastructure

**assignee:** codex
**status:** done
**priority:** normal
**remark:** ต้องทำก่อน indicator tasks ทุกตัว — เป็น foundation ทั้งหมด

**Why:** สร้าง foundation ให้ระบบคำนวณ indicator ทุกตัวแบบ event-driven ทุกครั้งที่ trade เปิด แล้วบันทึกว่า signal match กับ direction ของ trade หรือไม่ — ใช้ bars ณ เวลา entry เพื่อให้ Phase 3 (Pattern Discovery) ใช้ข้อมูลที่ถูกต้อง
**Files to touch:**
- `api/alembic/versions/009_add_trade_indicator_signals.py` (New)
- `api/models/indicator_signal.py` (New) — ORM model
- `api/schemas/indicator_signal.py` (New) — Pydantic schema
- `api/services/indicator_engine.py` (New) — REGISTRY + compute_all()
- `api/services/indicators/__init__.py` (New)
- `api/routers/indicator_signals.py` (New) — GET /api/indicator-signals/{trade_id}
- `api/services/trade_logger.py` (Modify) — wire background task on entry only
- `api/main.py` (Modify) — register router
- `api/requirements.txt` (Modify) — เพิ่ม pandas-ta
- `tests/test_indicator_engine.py` (New)
**Acceptance criteria:**
- [ ] Migration 009 สร้าง `trade_indicator_signals` table: `(id UUID, trade_id UUID FK, indicator_slug VARCHAR, timeframe VARCHAR, value FLOAT, direction VARCHAR, matched BOOL, metadata JSONB, calculated_at TIMESTAMPTZ)`
- [ ] `IndicatorResult` dataclass มี field: `slug, value, direction, matched, timeframe, metadata`
- [ ] `REGISTRY: dict[str, IndicatorFn]` + `@register("slug")` decorator ใช้งานได้
- [ ] `compute_all(trade, bars_by_tf) -> list[IndicatorResult]` รันทุก indicator ใน REGISTRY
- [ ] `trade_logger.py` เรียก `asyncio.create_task(compute_all(...))` เฉพาะเมื่อ `order_state = filled` AND `open_price is not None` AND `close_price is None` — trigger ที่ entry เท่านั้น ห้าม trigger ซ้ำตอน close
- [ ] `bars_by_tf` ที่ส่งเข้า `compute_all` ต้องเป็น bars ที่ fetch โดยใช้ `trade.open_time` เป็น anchor — ไม่ใช่ bars ล่าสุด ณ เวลา compute
- [ ] ถ้า trade นั้นมี `trade_indicator_signals` อยู่แล้ว (recompute กรณี history sync) → ลบของเก่าแล้วเขียนใหม่แทน overwrite ไม่ได้แค่ append
- [ ] `GET /api/indicator-signals/{trade_id}` คืน list ของ signals ที่ match trade นั้น
- [ ] `pip install pandas-ta` เพิ่มใน requirements.txt
- [ ] pytest ผ่านทุก test (รวม regression)
**Verify:**
```bash
cd api && alembic upgrade head
cd api && pytest ../tests/ -v
curl "http://localhost:8000/api/indicator-signals/{some-trade-id}"
```

---

### TASK: Indicator tasks — Trend (29) + Momentum (39)

**assignee:** codex
**status:** done
**priority:** normal
**remark:** อ่าน `.agents/indicators/README.md` ก่อน — มี Pickup Rule + architecture. Task files อยู่ที่ `.agents/indicators/trend.md` (IND-T-01..29) และ `.agents/indicators/momentum.md` (IND-M-01..39) — หยิบทีละ group, อัปเดต assignee+status ในไฟล์นั้นก่อน start. Infrastructure (REGISTRY, IndicatorResult, compute_all) เสร็จแล้วจาก Task #5.

**Why:** ต้องมี indicator logic ครบ 68 ตัวใน REGISTRY เพื่อให้ Phase 3 Pattern Discovery มีข้อมูลพอวิเคราะห์ pattern
**Files to touch:**
- `api/services/indicators/trend/{slug}.py` (New × 29) — ดู slug ในแต่ละ task ใน trend.md
- `api/services/indicators/momentum/{slug}.py` (New × 39) — ดู slug ในแต่ละ task ใน momentum.md
- `tests/test_indicators_trend.py` (New) — รวม tests ของ trend group ทั้งหมด
- `tests/test_indicators_momentum.py` (New) — รวม tests ของ momentum group ทั้งหมด
**Acceptance criteria:**
- [ ] ทุก indicator ลงทะเบียนใน REGISTRY ด้วย `@register("slug")`
- [ ] ทุก indicator คืน `IndicatorResult` ที่มี `slug, value, direction, matched, timeframe, metadata` ครบ
- [ ] `matched=True` เมื่อ direction ตรงกับ trade direction ตามเงื่อนไขใน task file แต่ละตัว
- [ ] `direction` คืน `"bullish"` | `"bearish"` | `"neutral"` เท่านั้น
- [ ] pytest ผ่านทุก test รวม regression (ใช้คำสั่ง Verify ด้านล่าง)
**Verify:**
```bash
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_indicators_trend.py tests/test_indicators_momentum.py -v"
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/ -v --tb=short"
```

---

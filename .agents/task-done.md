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

### TASK: Add missing MCP endpoints (account-snapshots, price-bars)

**assignee:** codex
**status:** done
**priority:** low
**remark:** codex flagged this in feedback.md — 2 MCP tools reference endpoints that don't exist yet: `/api/account-snapshots` and `/api/price-bars`. Tools work but return 404 until implemented.

**Why:** `get_account_history` and `get_price_context` MCP tools call endpoints that aren't implemented — they 404 silently and return error strings
**Files to touch:**
- `api/routers/account.py` (Modify) — add `/api/account-snapshots?days=N` endpoint
- `api/routers/price_tick.py` or new `price_bars.py` (Modify/New) — add `/api/price-bars?symbol=&tf=&limit=` endpoint
- `tests/test_trader_profile.py` or new test file (Modify/New) — test the new endpoints
**Acceptance criteria:**
- [ ] `GET /api/account-snapshots?days=7` returns list of AccountSnapshot rows for the last N days, filtered by current account
- [ ] `GET /api/price-bars?symbol=XAUUSD&tf=M15&limit=50` returns list of PriceBar rows
- [ ] Both endpoints return empty list (not 404) when no data
- [ ] MCP `get_account_history` and `get_price_context` tools return valid JSON
**Verify:**
```bash
curl "http://localhost:8000/api/account-snapshots?days=7"
curl "http://localhost:8000/api/price-bars?symbol=XAUUSD&tf=M15&limit=10"
cd api && pytest ../tests/ -v
```

---

### TASK: Indicator tasks — Volume (19) + Volatility (15) + S&R (18) + Pattern (9) + Cycle (13)

**assignee:** codex
**status:** done
**priority:** low
**remark:** แต่ละ group ทำ parallel ได้ — agent หยิบได้ทีละ 1 group ตาม Pickup Rule ใน `.agents/indicators/README.md`. อัปเดต assignee+status ในไฟล์ group นั้นก่อน start ห้าม parallel ภายใน group เดียวกัน. Infrastructure (REGISTRY, IndicatorResult, common.py pattern) เสร็จแล้ว ดู `api/services/indicators/trend/` เป็น reference.

**Why:** ครบ 142 indicators ใน REGISTRY เพื่อให้ Phase 3 Pattern Discovery มีข้อมูลครบสำหรับวิเคราะห์ทุก combination
**Files to touch (per group):**
- Volume: `api/services/indicators/volume/{slug}.py` (×19) — ดู `.agents/indicators/volume.md`
- Volatility: `api/services/indicators/volatility/{slug}.py` (×15) — ดู `.agents/indicators/volatility.md`
- S&R: `api/services/indicators/sr/{slug}.py` (×18) — ดู `.agents/indicators/sr.md`
- Pattern: `api/services/indicators/pattern/{slug}.py` (×9) — ดู `.agents/indicators/pattern.md`
- Cycle: `api/services/indicators/cycle/{slug}.py` (×13) — ดู `.agents/indicators/cycle.md`
- `tests/test_indicators_{group}.py` (New per group)
**Acceptance criteria:**
- [ ] ทุก indicator ลงทะเบียนใน REGISTRY ด้วย `@register("slug")`
- [ ] ทุก indicator คืน `IndicatorResult` ที่มี `slug, value, direction, matched, timeframe, metadata` ครบ
- [ ] `matched=True` ตามเงื่อนไขในแต่ละ task file
- [ ] `direction` คืน `"bullish"` | `"bearish"` | `"neutral"` เท่านั้น
- [ ] pytest ผ่านทุก test รวม regression
**Verify:**
```bash
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_indicators_{group}.py -v"
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/ -v --tb=short"
```

---

### TASK: Pattern Discovery Engine (Phase 3)

**assignee:** codex
**status:** done
**priority:** normal
**remark:** blocks กับ Task #5–12 (Indicator Engine ต้องเสร็จและมี entry-time signals สะสมไว้พอก่อน) — spec อยู่ที่ `docs/superpowers/specs/2026-05-24-pattern-discovery-auto-paper-trader-design.md`

**Why:** วิเคราะห์ entry-time indicator signals หา combinations ที่ correlate กับ winning trades แล้ว spawn paper_trader_rules อัตโนมัติ
**Files to touch:**
- `api/alembic/versions/010_add_patterns.py` (New) — patterns + paper_trader_rules tables
- `api/models/pattern.py` (New) — Pattern, PaperTraderRule ORM
- `api/schemas/pattern.py` (New) — Pydantic schemas
- `api/services/pattern_discovery.py` (New) — discovery algorithm + dedup
- `api/routers/patterns.py` (New) — GET /api/patterns, /api/paper-trader-rules
- `api/main.py` (Modify) — APScheduler cron + register router
- `api/requirements.txt` (Modify) — เพิ่ม apscheduler
- `tests/test_pattern_discovery.py` (New)
**Acceptance criteria:**
- [ ] Migration 010 สร้าง `patterns` table: `(id UUID, indicator_slugs VARCHAR[], timeframe VARCHAR, win_rate FLOAT, sample_count INT, consecutive_stable_days INT, status VARCHAR, discovered_at TIMESTAMPTZ, promoted_at TIMESTAMPTZ)`
- [ ] Migration 010 สร้าง `paper_trader_rules` table: `(id UUID, pattern_id UUID FK, status VARCHAR, spawned_at TIMESTAMPTZ, total_trades INT, win_count INT)`
- [ ] Window ใช้ dual-constraint: last `DISCOVERY_WINDOW_TRADES` (default 50) trades แต่ไม่เกิน `DISCOVERY_WINDOW_MAX_DAYS` (default 30) วัน — เอา cutoff ที่ recent กว่า
- [ ] ทั้ง 5 threshold config ผ่าน env vars: `DISCOVERY_WINDOW_TRADES`, `DISCOVERY_WINDOW_MAX_DAYS`, `DISCOVERY_MIN_SAMPLE` (10), `DISCOVERY_MIN_WIN_RATE` (0.60), `DISCOVERY_STABLE_DAYS` (3)
- [ ] `run_pattern_discovery()` generate combinations ขนาด 2–5 slugs จาก matched signals ของแต่ละ trade
- [ ] combinations ที่ sample < `DISCOVERY_MIN_SAMPLE` หรือ win_rate < `DISCOVERY_MIN_WIN_RATE` ไม่ถูก promote
- [ ] `consecutive_stable_days` เพิ่มขึ้นทุกวันที่ผ่าน threshold, reset เป็น 0 เมื่อไม่ผ่าน
- [ ] pattern ที่ `consecutive_stable_days >= DISCOVERY_STABLE_DAYS` → promote เป็น `status=active`
- [ ] Dedup: Jaccard similarity > 0.8 กับ active paper_trader_rule ใดก็ตาม → skip
- [ ] pattern active ใหม่ที่ผ่าน dedup → สร้าง `paper_trader_rule` status=active อัตโนมัติ
- [ ] APScheduler รัน `run_pattern_discovery()` ทุกวันตอน 00:00 UTC
- [ ] `GET /api/patterns` และ `GET /api/paper-trader-rules` คืนข้อมูลถูกต้อง
- [ ] pytest ผ่านทุก test รวม regression
**Verify:**
```bash
cd api && alembic upgrade head
cd api && pytest ../tests/test_pattern_discovery.py -v
cd api && pytest ../tests/ -v
curl "http://localhost:8000/api/patterns"
curl "http://localhost:8000/api/paper-trader-rules"
```

---

### TASK: Auto Paper Trader (Phase 4)

**assignee:** codex
**status:** done
**priority:** normal
**remark:** blocks กับ Task #13 (Pattern Discovery ต้องเสร็จและมี active paper_trader_rules ก่อน) — spec อยู่ที่ `docs/superpowers/specs/2026-05-24-pattern-discovery-auto-paper-trader-design.md`

**Why:** monitor live prices ทุก 60 วินาที auto entry paper trade เมื่อ pattern conditions ครบ และ exit ด้วย Hybrid strategy (S/R TP + momentum flip + ATR SL)
**Files to touch:**
- `api/services/paper_trader.py` (New) — in-memory cache + signal monitor + exit manager
- `api/routers/market_tick.py` (Modify) — เพิ่ม `asyncio.create_task(_run_paper_trader())`
- `api/routers/patterns.py` (Modify) — เพิ่ม `GET /api/paper-trades`
- `tests/test_paper_trader.py` (New)
**Acceptance criteria:**
- [ ] `_run_paper_trader()` ถูก trigger เป็น background task ทุกครั้งที่ POST /api/market-tick
- [ ] in-memory rule cache: load active rules จาก DB เฉพาะเมื่อ TTL expired (1 ชั่วโมง) ไม่ใช่ทุก tick
- [ ] Signal Monitor compute เฉพาะ indicator slugs ที่อยู่ใน active rules เท่านั้น (ไม่ใช่ทั้ง 142)
- [ ] Entry guard: ไม่สร้าง paper trade ถ้า rule นั้นมี open paper trade อยู่แล้ว (1 rule = 1 open trade)
- [ ] TP คำนวณจาก nearest pivot S/R level ในทิศที่ถูกต้อง (R1/R2 สำหรับ buy, S1/S2 สำหรับ sell)
- [ ] SL = ATR(14) × 1.5 จาก entry price
- [ ] Exit Manager เช็ค TP/SL ก่อน (O(1)) แล้วค่อยเช็ค momentum flip
- [ ] paper trade ปิดเมื่อ price hit TP (win), hit SL (loss), หรือ momentum indicator พลิก (early exit)
- [ ] `paper_trader_rules.win_count` และ `total_trades` อัปเดตเมื่อ trade ปิด
- [ ] `GET /api/paper-trades` คืน list paper trades (open + closed) พร้อม rule_id
- [ ] tick processing รวม < 2 วินาที (วัดจาก test ที่ mock bars และ mock rules)
- [ ] pytest ผ่านทุก test รวม regression
**Verify:**
```bash
cd api && pytest ../tests/test_paper_trader.py -v
cd api && pytest ../tests/ -v
curl "http://localhost:8000/api/paper-trades"
# ส่ง mock tick แล้วเช็คว่า background task รัน:
curl -X POST http://localhost:8000/api/market-tick -H "Content-Type: application/json" -d '{...}'
```

---

### TASK: Paper Trade Console — show richer per-rule context (Paper Rule Drawer)

**assignee:** claude
**status:** done
**priority:** normal
**remark:** shipped 2026-05-26 as Paper Rule Drawer — spec `docs/superpowers/specs/2026-05-26-paper-rule-drawer-design.md`, plan `docs/superpowers/plans/2026-05-26-paper-rule-drawer.md`. 12 commits e28b307..9b4b264 on feat/paper-trade-v2. 337/337 tests, clean build.

**Why:** PaperRuleCard อ่านยาก ดูแล้วบอกไม่ได้ว่ารูล alive/stuck/failing — เพิ่ม collapsed summary (alive dot + balance + cum PnL + open count) + click-to-expand drawer ที่รวบ 6 sections (signal trail, active orders, recent history, pattern conditions, promotion gates, shadows) ใน UI เดียว
**Files touched:**
- `api/schemas/pattern.py` — added 4 fields to `PaperTraderRuleResponse`
- `api/routers/patterns.py` — batched `_open_trades_count_by_rule` + `_last_activity_by_rule`
- `frontend/src/components/PaperRuleCard.jsx` — collapsed redesign + caret
- `frontend/src/components/PaperRuleDrawer.jsx` — 6-section drawer shell
- `frontend/src/components/drawer/{SignalTrail,OrdersTable,PatternConditions,PromotionGates,ShadowsList}.jsx` — sections
- `frontend/src/hooks/usePaperSignals.js` — `usePaperRuleDetail` hook with cancellation token
- `tests/test_paper_trader_rules_extended.py` — 3 tests covering new fields
**Acceptance criteria:**
- [x] Card collapsed shows balance + cum PnL + open count + alive dot
- [x] Caret expands drawer with 6 sections (skip empty sections gracefully)
- [x] Manual refresh refetches all 4 drawer endpoints
- [x] Shadow rules surfaced inside parent drawer (not as standalone cards)
- [x] Backend pytest passes including regression
- [x] Drawer queries fire only when expanded (no auto-poll)
**Verify:**
```bash
cd api && pytest ../tests/test_paper_trader_rules_extended.py -v
cd frontend && npm run build
```

---

### TASK: Migrate legacy paper_exit_strategy labels to "rule_driven"

**assignee:** codex (done by claude)
**status:** done
**priority:** low
**remark:** shipped 2026-05-26 as migration 019 (commit 0c509c4). Normalized 58 legacy rows (`tp:*;sl:*`) → `rule_driven` in prod; idempotent re-run verified via downgrade+upgrade.

---

### TASK: Add /api/market-tick integration test for mirror exit path

**assignee:** codex (done by claude)
**status:** done
**priority:** low
**remark:** shipped 2026-05-26 (commit c50f908). New test `test_market_tick_closes_open_mirror_via_pivot_tp` seeds D/H1 bars + mirror trade, posts tick, asserts `closed_mirror == 1` and `paper_exit_reason == 'tp_pivot'`. Regression validated by temporarily disabling `evaluate_mirror_exits` (test failed as expected).

---

### TASK: Tighten ORM nullability for paper_trader_rules.filters and gate_status

**assignee:** codex (done by claude)
**status:** done
**priority:** low
**remark:** shipped 2026-05-26 as migration 020 (commit 73c6b84). NULL backfill + `ALTER COLUMN ... SET NOT NULL` on `filters` and `gate_status`; sqlite path no-op for tests. ORM `Mapped[list]` / `Mapped[dict]` declarations now match DB. 338/338 tests pass.

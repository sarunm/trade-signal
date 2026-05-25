# Task Backlog

**Obsidian Knowledge Base:** ก่อนเริ่ม task ใดก็ตาม ให้อ่าน `/Users/nick/Obsidian Vault/agents/INDEX.md` ก่อนเสมอ — ดูว่าต้องอ่านไฟล์ไหนต่อ แล้วอ่านเฉพาะไฟล์นั้น

**Persistent Rules:** อ่าน `.agents/RULES.md` ก่อนเริ่ม task เสมอ — มี lessons จาก bugs และ reviews ที่ผ่านมา

**Roles:** Claude — design + assign + PR review + merge + retro. Codex / agy — implement only.

**Workflow:**
1. Claude assigns `assignee` (codex|agy) and sets `status: pending` before dispatching
2. Agent picks **only** tasks where `assignee` matches their name
3. Agent creates branch: `git checkout -b <assignee>/<task-slug>` และ updates `status: in_progress`
4. **Contract confirmation:** ก่อนเขียนโค้ด agent ต้อง output CONTRACT block ก่อนเสมอ (ดู format ด้านล่าง)
5. Implements per acceptance criteria
6. Runs all verify commands — **all must pass before continuing**
7. Commits, opens PR to `main` via `gh pr create`
8. Updates `status: done` + writes `.agents/handoff.md` พร้อม PR URL
9. Claude reads `.agents/feedback.md` + reviews PR diff
10. Approved → Claude merges PR + **runs retro** → เพิ่ม lessons ใน `.agents/RULES.md` ถ้ามี
11. Bugs found → Claude creates `[BUG]` task, requests changes on PR

**Branch naming:** `codex/<task-slug>` หรือ `agy/<task-slug>` เช่น `agy/fib-pp-weekly`

**Status values:** `pending` → `in_progress` → `done` | `blocked`

**Priority values:** `high` | `normal` | `low`

**"Fix later" rule:** ห้ามพูดว่า "แก้ทีหลัง" หรือ "เพิ่มทีหลัง" โดยไม่สร้าง task — ทุกครั้งที่ review เจอ deferred item ให้สร้าง task ทันทีพร้อม `priority: low` และ `remark:` อธิบายว่าทำไมถึง defer

**Bug rule:** Claude เจอ bug ระหว่าง review → สร้าง task ใหม่ prefix `[BUG]` พร้อม `blocks:` field ชี้ไปที่ task ต้นเหตุ อย่าแก้ inline

**Backlog rule (Claude):** ทุกครั้งที่เจอสิ่งที่ต้องทำ — ไม่ว่าจะเป็น bug, feature, หรือ deferred item — ให้เพิ่มลง backlog ทันที พร้อม `assignee` + `priority` ก่อนจะทำอย่างอื่นต่อ ห้าม defer โดยไม่มี task

**Priority rule (Agents):** Agent ต้อง pick task ที่ `priority: high` ก่อนเสมอ → `normal` → `low` ห้ามข้ามไปทำ task ที่ priority ต่ำกว่าถ้ายังมี high/normal ค้างอยู่

**Feedback rule:** Agent เจอ task แปลกๆ, scope ไม่ชัด, มีข้อแนะนำ, หรือ risk → เขียนใน `.agents/feedback.md` ก่อน open PR เสมอ

**Claude review:** Reads `.agents/feedback.md` → reviews PR → approves + merges หรือ requests changes

**Retro rule (Claude):** หลัง merge ทุก PR — ถ้าพบ bug, gotcha, หรือ assumption ผิด ให้เพิ่ม rule ใน `.agents/RULES.md` ทันที ไม่ต้องรอสะสม format: `## RULE-N | <title>` + `**Lesson:**` + `**Apply when:**`

**Contract format:** Agent ต้อง output block นี้ก่อนเขียนโค้ดเสมอ:
```
CONTRACT
task: <task title>
will touch: <files>
will NOT touch: <files ที่ไม่แตะ>
AC understood:
  - <echo back แต่ละ AC item>
assumptions: <ถ้ามี หรือ none>
```

---

## สารบัญ

| # | Task | Assignee | Priority | Status |
|---|---|---|---|---|
| 1 | Trader Profile MCP — Phase 1 | codex | 🟢 normal | done |
| 2 | Trade Advisor — entry scoring + recovery map + live zone alerts | agy | 🟢 normal | done |
| 3 | Migrate agent task system to file-per-task | claude | 🔵 low | pending |
| 4 | Add missing MCP endpoints (account-snapshots, price-bars) | codex | 🔵 low | pending |
| 5 | Indicator Engine Infrastructure | codex | 🟢 normal | done |
| 6–7 | Indicator tasks: Trend (29) + Momentum (39) | codex | 🟢 normal | done |
| 8–12 | Indicator tasks: Volume✅/Volatility✅/S&R✅/Pattern✅/Cycle✅ (142/142) | codex/claude | 🔵 low | done |
| BUG-1 | [BUG] Trade direction always wrong — EA sends ENTRY_OUT deal type | claude | 🔴 high | done |
| 13 | Pattern Discovery Engine (Phase 3) | claude | 🟢 normal | done |
| 14 | Auto Paper Trader (Phase 4) | claude | 🟢 normal | done |

**Indicator tasks:** ดู [`.agents/indicators/`](.agents/indicators/README.md) — 1 indicator 1 task

**Done tasks:** ดู [archive.md](archive.md)

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
**status:** in_progress
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

### TASK: Migrate agent task system to file-per-task

**assignee:** claude
**status:** pending
**priority:** low
**remark:** ⚠️ ก่อนทำต้องคุยกับ user ละเอียดก่อน — ยังไม่ได้ตัดสินใจ design สุดท้าย (naming convention, rules file placement, migration strategy)

**Why:** backlog.md เดียวทำให้ agent ต้องอ่านทั้งไฟล์เพื่อหา task ตัวเอง — file-per-task + status ใน filename ช่วยลด token ได้มาก
**Files to touch:**
- `.agents/tasks/` (new directory)
- `.agents/backlog.md` (migrate + archive)
- `.agents/RULES.md` (extract workflow rules)
**Acceptance criteria:**
- TBD — ออกแบบหลังคุยกับ user แล้ว
**Verify:**
- TBD

---

### TASK: Add missing MCP endpoints (account-snapshots, price-bars)

**assignee:** codex
**status:** pending
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

### TASK: Indicator tasks — Volume (19) + Volatility (15) + S&R (18) + Pattern (9) + Cycle (13)

**assignee:** codex
**status:** in_progress
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
**status:** pending
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
**status:** pending
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

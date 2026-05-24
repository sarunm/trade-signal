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
| 5 | Indicator Engine Infrastructure | codex | 🟢 normal | pending |
| 6–7 | Indicator tasks: Trend (29) + Momentum (39) | codex | 🟢 normal | pending |
| 8–12 | Indicator tasks: Volume/Volatility/S&R/Pattern/Cycle (74) | (ว่าง) | 🔵 low | pending |
| BUG-1 | [BUG] Trade direction always wrong — EA sends ENTRY_OUT deal type | claude | 🔴 high | done |

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

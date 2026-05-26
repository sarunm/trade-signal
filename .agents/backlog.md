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
| 4 | Add missing MCP endpoints (account-snapshots, price-bars) | claude | 🔵 low | done |
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


### TASK: Tighten ORM nullability for paper_trader_rules.filters and gate_status

**assignee:** codex
**status:** pending
**priority:** low
**remark:** Migration 011 declares `filters` and `gate_status` as `nullable=True` on the DB side, but the ORM models in `api/models/pattern.py` declare them as non-Optional `Mapped[list]` / `Mapped[dict]`. Both columns have server_defaults, so the runtime risk is low (SQLAlchemy does not enforce Mapped types at runtime), but the type hint is misleading. Picked up during Plan 1 Task 1 code review.

**Why:** keep ORM type hints honest about nullability so future readers do not assume the columns are always populated.
**Files to touch:**
- `api/alembic/versions/011_paper_redesign_schema.py` — change kwargs to `nullable=False` for `filters` and `gate_status` (server_default already set)
- `api/models/pattern.py` — keep `Mapped[list]` / `Mapped[dict]` as-is
- `tests/test_migration_011.py` — optional: assert columns are NOT NULL
**Acceptance criteria:**
- [ ] Migration 011 sets `nullable=False` for `filters` and `gate_status`
- [ ] All existing tests still pass
- [ ] Existing rows in production DB get the server_default applied (no data loss)
**Verify:**
```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_migration_011.py tests/test_paper_trader.py -v"
```


### TASK: Migrate legacy paper_exit_strategy labels to "rule_driven"

**assignee:** codex
**status:** pending
**priority:** low
**remark:** Plan 2 Task 1 commit 026fa85 changed mirror trade spawns to write `paper_exit_strategy="rule_driven"`, but existing rows in the prod DB still hold structured labels like `tp:no_history;sl:no_history` from the legacy averaging code. Task surfaced during Plan 2 Task 1 review.

**Why:** keep the column single-vocabulary so dashboards/analytics filters don't have to special-case both schemes. Mirror exits from Plan 2 Task 2 onward only know "rule_driven".
**Files to touch:**
- `api/alembic/versions/0XX_normalize_mirror_exit_strategy.py` — new migration that updates `trades` rows where `is_paper=true AND paper_mode='mirror' AND paper_exit_strategy LIKE 'tp:%' OR 'sl:%'` to `'rule_driven'`
**Acceptance criteria:**
- [ ] Migration runs idempotently
- [ ] Affected rows updated; non-mirror or already-rule_driven rows untouched
- [ ] Downgrade is a no-op (cannot reconstruct lost label)
**Verify:**
```
docker compose run --rm api alembic upgrade head
docker compose exec db psql -U tradesignal -d tradesignal -c "SELECT paper_exit_strategy, COUNT(*) FROM trades WHERE is_paper=true GROUP BY 1;"
```


### TASK: Add /api/market-tick integration test for mirror exit path

**assignee:** codex
**status:** pending
**priority:** low
**remark:** Plan 2 Task 3 commit af72ebd flipped `tests/test_market_tick.py::test_market_tick_closes_matching_paper_trade_without_storing_tick` from `PaperMode.mirror` to `PaperMode.independent` so it kept passing under the new routing. Mirror behavior is covered by `tests/test_mirror_exit_manager.py`, but there is now no router-level test that proves `/api/market-tick` actually invokes `evaluate_mirror_exits` and reports `closed_mirror`. A small new test should add that integration coverage.

**Why:** detect future regressions where someone removes the mirror call from `market_tick.py` without breaking unit tests.
**Files to touch:**
- `tests/test_market_tick.py` — add `test_market_tick_closes_open_mirror_via_pivot_tp` (or similar) that seeds a mirror trade + price bars, posts a tick to `/api/market-tick`, and asserts response has `closed_mirror == 1`
**Acceptance criteria:**
- [ ] One new test that fails if `evaluate_mirror_exits` is removed from `market_tick.py`
- [ ] Test uses monkeypatching to bypass RSI computation if needed (matches pattern in `test_mirror_exit_manager.py`)
- [ ] Full suite stays green
**Verify:**
```
docker compose run --rm -v "$(pwd)/tests:/app/tests" -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/test_market_tick.py -v"
```


### TASK: Paper Trade Console — show richer per-rule context (hard to read right now)

**assignee:** claude
**priority:** normal
**status:** needs-design
**remark:** ผู้ใช้ feedback ว่า PaperRuleCard ใน Paper Trade Console ตอนนี้อ่านยาก ดูแล้วไม่แน่ใจว่ารูล "ผิดปกติ" หรือ "ทำงานถูกต้องอยู่" — เคยคุยกันก่อนหน้าว่าจะแสดงข้อมูลเยอะกว่านี้ แต่ยังไม่ได้ลงมือทำ

**Why:** rule card ปัจจุบันโชว์แค่ mode / tier / Net EV / Wilson / vs Baseline / trades / wins + filters chip — ไม่มี signal trail, ไม่มี last-trade outcome, ไม่มี link ไปดู trades ของรูล, ไม่มี shadow comparison ตัวเลข ทำให้ดูแล้วไม่รู้ว่ารูลกำลัง "alive" หรือ "stuck" อยู่

**Context (ไฟล์ที่เกี่ยวข้อง):**
- `frontend/src/components/PaperRuleCard.jsx` — UI card ปัจจุบัน
- `frontend/src/components/PaperTradeConsole.jsx` — list + tier filter
- `api/routers/patterns.py` — `/api/paper-trader-rules`, `/api/paper-trader-rules/{id}/shadows`, `/api/paper-trades`
- `api/schemas/pattern.py` — `PaperTraderRuleResponse`, `PaperTradeResponse`

**Open questions ต้อง brainstorm ก่อนลงมือ:**
1. อะไรคือ "อ่านยาก" จริง ๆ — field ที่อยากเห็นเพิ่ม คือ?
   - last 5 signal results (mini sparkline / dot trail)?
   - last trade time + last trade outcome (W/L + ฿)?
   - lifetime PnL ฿ (ไม่ใช่แค่ EV/trade)?
   - shadow vs parent winrate delta แบบ inline?
   - reason last signal เป็น `near` / `far` (gate fail reason)?
   - link / drawer ที่ขยายดู trades + recent ticks ของรูลนั้น?
2. card-level vs drawer-level — ขยาย card ให้ใหญ่ขึ้น หรือทำเป็น expandable drawer?
3. shadow rules ตอนนี้ถูก filter ออกจาก list (`status !== 'shadow'`) — อยากเห็น shadow nested ใต้ parent ไหม?

**Next step:** invoke `superpowers:brainstorming` ตอบคำถามทีละข้อ → spec → plan → execute (TDD per task)

**Acceptance criteria (จะ refine ตอน brainstorm):**
- [ ] ดู rule card แล้วบอกได้ใน 5 วิ ว่ารูล healthy / stuck / failing
- [ ] เห็น last activity (ไม่ต้อง refresh ก็รู้ว่ารูลยังเดินอยู่)
- [ ] เห็น shadow comparison ในที่เดียว ไม่ต้องเปิด tab ใหม่

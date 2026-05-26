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


<!-- Paper Trade Console — show richer per-rule context: shipped 2026-05-26 as Paper Rule Drawer (12 commits e28b307..9b4b264, 337/337 tests). Archived to task-done.md. -->

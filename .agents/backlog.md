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

### TASK: [BUG] Paper Trade Console — Cum PnL stuck at +฿0 (+0.0%)

**assignee:** claude
**status:** needs-design
**priority:** normal
**remark:** หลัง Paper Rule Drawer ship แล้ว user เห็นว่า Cum PnL ใน collapsed card แสดง `+฿0 (+0.0%)` ไม่ขยับเลย ทั้งที่มี trades ปิดไปแล้ว — สงสัย card คำนวณจาก `virtual_balance_current - virtual_balance_start` ซึ่งอาจไม่ถูก update หลัง trade ปิด หรือคำนวณผิด field

**Why:** ถ้า Cum PnL ไม่ขยับ user จะ debug ไม่ได้ว่ารูลทำเงินไหม — ทำให้ feature ใหม่ไร้ค่า
**Hypotheses ต้อง investigate:**
1. `paper_trader_rules.virtual_balance_current` ไม่ถูก update เมื่อ paper trade ปิด (close_trade flow)
2. Card คำนวณจาก field ที่ไม่ตรง — เช่น ใช้ rule field แทนที่จะ sum profit จาก closed trades ของรูล
3. PaperRuleCard render อ่าน field ที่ผิด หรือ default = balance_start เลยให้ผลลัพธ์ 0
**Files to investigate:**
- `frontend/src/components/PaperRuleCard.jsx` — Cum PnL render logic
- `api/services/paper_exit_manager.py` / `api/services/paper_trader.py` — close trade flow
- `api/services/mirror_exit_manager.py` — mirror close path
- `api/models/pattern.py` — virtual_balance_current field
- `api/routers/patterns.py` — list_paper_trader_rules response builder
**Acceptance criteria:**
- [ ] หา root cause ที่แท้จริง (ดู DB row จริง vs UI value)
- [ ] Cum PnL ใน card ขยับตาม trade ที่ปิด (positive ถ้า profit รวม > 0, negative ถ้าขาดทุน)
- [ ] เพิ่ม test ป้องกัน regression
**Verify:**
```bash
docker compose exec -T db psql -U tradesignal -d tradesignal -c "SELECT id, virtual_balance_start, virtual_balance_current, total_trades FROM paper_trader_rules LIMIT 5;"
docker compose exec -T db psql -U tradesignal -d tradesignal -c "SELECT recovery_plan->>'paper_trader_rule_id' AS rule_id, COUNT(*), SUM(profit) FROM trades WHERE is_paper=true AND close_time IS NOT NULL GROUP BY 1;"
```

---

<!-- 3 codex backlog tasks shipped 2026-05-26: migration 019 (legacy exit_strategy), test_market_tick integration test, migration 020 (NOT NULL filters/gate_status). Archived to task-done.md. -->

<!-- Paper Trade Console — show richer per-rule context: shipped 2026-05-26 as Paper Rule Drawer (12 commits e28b307..9b4b264, 337/337 tests). Archived to task-done.md. -->

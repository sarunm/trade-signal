# Task Backlog

**Roles:** Claude — design + assign + PR review + merge. Codex / agy — implement only.

**Workflow:**
1. Claude assigns `assignee` (codex|agy) and sets `status: pending` before dispatching
2. Agent picks **only** tasks where `assignee` matches their name
3. Agent creates branch: `git checkout -b <assignee>/<task-slug>` และ updates `status: in_progress`
4. Implements per acceptance criteria
5. Runs all verify commands — **all must pass before continuing**
6. Commits, opens PR to `main` via `gh pr create`
7. Updates `status: done` + writes `.agents/handoff.md` พร้อม PR URL
8. Claude reads `.agents/feedback.md` + reviews PR diff
9. Approved → Claude merges PR + pushes
10. Bugs found → Claude creates `[BUG]` task, requests changes on PR

**Branch naming:** `codex/<task-slug>` หรือ `agy/<task-slug>` เช่น `agy/fib-pp-weekly`

**Status values:** `pending` → `in_progress` → `done` | `blocked`

**Priority values:** `high` | `normal` | `low`

**"Fix later" rule:** ห้ามพูดว่า "แก้ทีหลัง" หรือ "เพิ่มทีหลัง" โดยไม่สร้าง task — ทุกครั้งที่ review เจอ deferred item ให้สร้าง task ทันทีพร้อม `priority: low` และ `remark:` อธิบายว่าทำไมถึง defer

**Bug rule:** Claude เจอ bug ระหว่าง review → สร้าง task ใหม่ prefix `[BUG]` พร้อม `blocks:` field ชี้ไปที่ task ต้นเหตุ อย่าแก้ inline

**Backlog rule (Claude):** ทุกครั้งที่เจอสิ่งที่ต้องทำ — ไม่ว่าจะเป็น bug, feature, หรือ deferred item — ให้เพิ่มลง backlog ทันที พร้อม `assignee` + `priority` ก่อนจะทำอย่างอื่นต่อ ห้าม defer โดยไม่มี task

**Priority rule (Agents):** Agent ต้อง pick task ที่ `priority: high` ก่อนเสมอ → `normal` → `low` ห้ามข้ามไปทำ task ที่ priority ต่ำกว่าถ้ายังมี high/normal ค้างอยู่

**Feedback rule:** Agent เจอ task แปลกๆ, scope ไม่ชัด, มีข้อแนะนำ, หรือ risk → เขียนใน `.agents/feedback.md` ก่อน open PR เสมอ

**Claude review:** Reads `.agents/feedback.md` → reviews PR → approves + merges หรือ requests changes

---

## สารบัญ

| # | Task | Assignee | Priority | Status |
|---|---|---|---|---|
| 1 | [BUG] Fix undeclared g_last_market_tick_sent in EA | codex | 🔴 high | pending |
| 2 | Trader Profile MCP — Phase 1 | agy | 🟢 normal | pending |
| 3 | Trade Advisor — entry scoring + recovery map + live zone alerts | agy | 🟢 normal | blocked |
| 4 | [BUG] Fix fib_level model JSON → JSONB | codex | 🟡 low | pending |

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
**status:** pending
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

### TASK: [BUG] Fix undeclared g_last_market_tick_sent in EA

**assignee:** codex
**status:** done
**priority:** high
**blocks:** [BUG] Redesign Fib levels to match ROM indicator — PP method, Weekly period

**Why:** found during review of commit 6fc99cb — EA will not compile
**Root cause:** `g_last_market_tick_sent` declaration was deleted from globals but usages at lines 458 + 502 remain
**Files to touch:**
- `ea/TradeSignalBridge.mq5` — เพิ่ม `datetime g_last_market_tick_sent = 0;` กลับในส่วน global declarations (บรรทัดเดียวกับ `g_last_sent_week_time`)
**Acceptance criteria:**
- [x] EA compiles ไม่มี undeclared identifier error
- [x] `g_last_market_tick_sent` declared ใน global scope
**Verify:**
Manual compile ใน MT5 Editor — ไม่มี error

---

### TASK: Trader Profile MCP — Phase 1 implementation

**assignee:** agy
**status:** pending
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
**status:** blocked
**priority:** normal
**remark:** รอ spec เขียนเสร็จก่อน — จะ unblock เมื่อ spec commit แล้ว

**Why:** ให้ระบบช่วย evaluate entry, แสดง recovery plan ตาม fib levels, และ alert เมื่อ price เข้า zone
**Files to touch:**
- TBD — รอ spec
**Acceptance criteria:**
- TBD — รอ spec

---

### TASK: [BUG] Fix fib_level model uses JSON instead of JSONB

**assignee:** codex
**status:** done
**priority:** low
**remark:** ทำงานได้แต่ inconsistent กับ DB type จริง — defer ได้แต่ควรแก้ก่อน migrate production
**blocks:** [BUG] Redesign Fib levels to match ROM indicator — PP method, Weekly period

**Why:** found during review of commit 6fc99cb — `api/models/fib_level.py` declares `resistance` + `support` เป็น `JSON` แต่ DB columns เป็น `JSONB` จาก migration 004
**Root cause:** Codex ใช้ `JSON` แทน `JSONB` ตอน redesign model
**Files to touch:**
- `api/models/fib_level.py` — เปลี่ยน `mapped_column(JSON, ...)` เป็น `mapped_column(JSONB, ...)` ทั้ง 2 columns + import `from sqlalchemy.dialects.postgresql import JSONB`
**Acceptance criteria:**
- [x] `resistance` + `support` ใน model ใช้ `JSONB`
- [x] `pytest tests/ -v` passes
**Verify:**
```bash
cd api && pytest ../tests/test_fib_levels.py -v
```

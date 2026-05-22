# Task Backlog

**Obsidian Knowledge Base:** ก่อนเริ่ม task ใดก็ตาม ให้อ่าน `/Users/nick/Obsidian Vault/agents/INDEX.md` ก่อนเสมอ — ดูว่าต้องอ่านไฟล์ไหนต่อ แล้วอ่านเฉพาะไฟล์นั้น

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
| 1 | Trader Profile MCP — Phase 1 | codex | 🟢 normal | in_progress |
| 2 | Trade Advisor — entry scoring + recovery map + live zone alerts | agy | 🟢 normal | done |
| 3 | Migrate agent task system to file-per-task | claude | 🔵 low | pending |

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

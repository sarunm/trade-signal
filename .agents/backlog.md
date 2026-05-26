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

### TASK: Explore ML to assist pattern discovery / signal scoring

**assignee:** claude
**priority:** low
**status:** needs-design
**remark:** idea ระหว่าง brainstorm dashboard re-design (2026-05-26) — เก็บไว้ก่อน ยังไม่ตัดสินใจ

**Why:** ตอนนี้ Pattern Discovery Engine เป็น brute-force combinations + threshold (sample ≥ 10, win rate ≥ 0.60, stable ≥ 3 วัน) อยากดูว่า ML ช่วยอะไรได้บ้าง — จัด priority candidate combos / classify trade outcome / score live entries / predict ruin

**Open questions (ต้อง brainstorm ก่อน scope):**
- ใช้ ML แทนที่ pattern discovery หรือเป็น layer เสริม?
- ใช้กับอะไร: (a) entry scoring, (b) exit timing, (c) basket size, (d) ranking pattern candidates, (e) anomaly detection (ruin warning)?
- ต้อง training data เท่าไหร่ — trade history ตอนนี้ยังน้อย
- Online learning vs batch retrain?
- Model อะไร — XGBoost / LightGBM (tabular), หรือ logistic regression ก่อน
- จะ deploy ยังไงใน Docker stack — joblib persistence? ONNX? FastAPI service แยก?
- Explainability — pattern ปัจจุบันอ่านง่าย ("rsi+ema match → bullish") ML จะกลายเป็น black box?

**Files to touch:** TBD ระหว่าง design

**Acceptance criteria:** TBD ระหว่าง design

**Verify:** TBD

---

### TASK: [BUG] Paper trades open without paper_trader_rule_id → orphan, exit logic skips them

**assignee:** codex
**priority:** high
**status:** pending

**Why:** Found 14 open paper trades in DB with `paper_trader_rule_id IS NULL` (1 independent + 13 mirror, opened 2026-05-18 to 2026-05-26). `paper_trader._check_exits` iterates `open_by_rule[rule_id]` so orphaned trades are never evaluated for TP/SL/momentum_flip. They sat open for 8 days. User force-closed all 14 at open_price (`paper_exit_reason='force_close_orphan'`) on 2026-05-26 to reset paper book.

**Root cause hypotheses (verify which):**
1. `paper_trader.spawn_trade` (or wherever `independent` mode opens trades) misses setting `paper_trader_rule_id` — check #779778800010 path
2. `mirror_trader.open_mirror_trade` doesn't write `paper_trader_rule_id` — 13 mirror trades all have it NULL
3. Migration 011 added the column but historical inserts didn't backfill — but these are NEW inserts post-migration
4. Symbol mismatch (XAUUSD vs GOLD#) preventing tick-driven exits — separate bug, log if confirmed

**Files to investigate:**
- `api/services/paper_trader.py` — spawn path for `independent` mode
- `api/services/mirror_trader.py` — `open_mirror_trade` rule_id assignment
- `api/services/mirror_exit_manager.py` — does it require `paper_trader_rule_id` to look up rule, or work via pattern?
- `api/models/trade.py` — is `paper_trader_rule_id` nullable=True in ORM (allowed) but should be NOT NULL for paper?

**Acceptance criteria:**
- [ ] Identify which spawn path drops `paper_trader_rule_id` (file:function)
- [ ] Add NOT NULL invariant test: any new paper trade insertion without rule_id raises (or backfill from rule context)
- [ ] Run test fixture that opens an `independent` paper trade and a mirror paper trade — both have `paper_trader_rule_id` populated
- [ ] Add migration 021: backfill `paper_trader_rule_id` for any future orphans by joining via pattern_id + spawn_strategy (or document why this can't be done safely)

**Verify:**
```
docker compose run --rm -e PYTHONPATH=/app api sh -c "cd /app && pytest tests/ -k 'paper_trader or mirror' -v"
docker compose exec db psql -U tradesignal -d tradesignal -c "SELECT COUNT(*) FROM trades WHERE is_paper=true AND paper_trader_rule_id IS NULL AND close_time IS NULL;"
# Expect: 0
```

**Remark:** Symptom appeared in dashboard browser smoke test 2026-05-26 — `basket_5k` rule drawer showed Active Order #779778800010 (BUY @3280.90, opened 2026-05-26 07:00 UTC) with no TP/SL/exit_strategy and no rule_id. Pattern (`indicator_slugs={}`, status=baseline) compounded the issue: even if rule_id were set, no momentum indicator means momentum_flip exit can't fire either. Look at why `basket_5k` rule got promoted/spawned with empty indicator_slugs.

---

<!-- [BUG] Cum PnL stuck at +฿0: shipped 2026-05-26 — cum_pnl_realized field derived from SUM(profit), close flow updates virtual_balance_current. Archived. -->

<!-- 3 codex backlog tasks shipped 2026-05-26: migration 019 (legacy exit_strategy), test_market_tick integration test, migration 020 (NOT NULL filters/gate_status). Archived to task-done.md. -->

<!-- Paper Trade Console — show richer per-rule context: shipped 2026-05-26 as Paper Rule Drawer (12 commits e28b307..9b4b264, 337/337 tests). Archived to task-done.md. -->

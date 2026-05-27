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

<!-- Pending Orders panel: shipped 2026-05-27 — /api/trades?state=pending + basket_with_pending projection in /api/trade-advisor + PendingOrders.jsx card under OpenPositions + WithPendingProjection row in BasketExitPlan; 366/366 tests pass. -->

---

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

<!-- BasketExitPlan UI/data fixes: shipped 2026-05-26 — BUY/SELL color, lot tooltip, mean_entry vs basket_be split (commit on feat/paper-trade-v2). Legacy trades #999001/#111001 force-closed earlier same day. -->

<!-- TopBar XAUUSD + Account + 1s refresh: shipped 2026-05-26 — symbol GOLD#, /api/header-snapshot, 1s polling, layout Account/Balance/%/Float/Equity/today, 5 tests. -->

<!-- OpenPositions + BasketExitPlan equal card heights: shipped 2026-05-26 — h-full added on both outer containers. -->

### TASK: ~~TopBar — fix XAUUSD price source + add Account block + 1-sec refresh~~ DONE

**assignee:** claude
**priority:** high
**status:** done

**Why:** TopBar แสดง `XAUUSD 3280.90` ซึ่งเป็น stale (M5 latest 2026-05-17 frozen). Live broker price = GOLD# 4577.37 (latest 2026-05-26). symbol mismatch ระหว่าง paper trades (XAUUSD) กับ live data (GOLD#) ทำให้ basket.current ผิด. นอกจากนั้นอยากเพิ่ม Account block ใน TopBar.

**Required layout (left → right):**
```
Account {account_number}  Balance: {balance}  Percent: {x.xx%}  Float P/L: {±฿n}  XAUUSD {price}
```
- `account_number` = `account.account_id`
- `balance` = `account.balance`
- `percent` = % change ของ equity จาก balance หรือ today profit_pct (ตัดสินใจระหว่าง impl — ดู spec ให้ชัด)
- `float P/L` = `account.floating_pl`

**XAUUSD price fix:** ตอนนี้ใช้ `advisor.data.basket.current` มาจาก `_aggregate_basket(latest_close)` ของ symbol `XAUUSD` ที่ frozen. ต้อง:
- ตัดสินใจ: ถาม backend คืน live `GOLD#` price แยกเป็น endpoint ใหม่ (`/api/market-tick/latest`) หรือ resolve symbol mapping ที่ backend (XAUUSD ↔ GOLD#) แล้ว basket query latest จาก correct symbol
- หรือใช้ EA tick ตรงๆ จาก market_tick handler

**Refresh interval (header only):** อยากให้ refresh ทุก 1 วินาที (ตอนนี้ account=3s, ea=5s, advisor=30s).
- Performance impact: 1 req/วิ × 3 endpoints (account, ea, advisor) = 3 req/วิ จาก browser → API → DB. ส่วนใหญ่เป็น single-row latest query ตาม index, น่าจะเบามาก (<5ms/req).
- Risk: advisor endpoint หนักกว่า (basket aggregation + pnl_summary loop) → ถ้ายิงทุก 1 วิอาจ load DB
- Recommend: ทำ `/api/header-snapshot` endpoint รวม (equity/balance/floating_pl/account_id/xau_price/ea_status) เป็น single query → 1 req/วิ พอ + cached

**Files to touch:**
- `frontend/src/components/TopBar.jsx` — add Account block, restructure layout
- `frontend/src/App.jsx` — fetch interval to 1000, fix xauPrice source
- (option) `api/routers/account.py` — add `/api/header-snapshot` lite endpoint
- `api/services/trade_logger.py` หรือ `api/services/price_handler.py` — resolve XAUUSD↔GOLD# symbol mismatch

**Open questions (ต้อง decide ก่อน impl):**
1. Symbol mismatch: เป็น bug ที่ EA ส่ง bars เป็น `GOLD#` แต่ trades เก็บเป็น `XAUUSD`? ดู `OnTimer` ใน `ea/TradeSignalBridge.mq5`
2. `Percent` ใน TopBar = อะไร? today PnL % / equity vs balance / drawdown from peak?
3. ทำ header-snapshot endpoint หรือยิงหลาย endpoint แบบเดิม?

**Acceptance criteria:**
- [ ] TopBar แสดง Account / Balance / Percent / Float P/L / XAUUSD price ตาม layout ด้านบน
- [ ] XAUUSD price = live broker price (วันนี้ 4577.x ไม่ใช่ 3280.90 frozen)
- [ ] Refresh ทุก 1 วินาที สำหรับ data ใน header เท่านั้น
- [ ] DevTools Network: <5 req/วิ จาก header (ไม่กระทบ section อื่น)
- [ ] DB query <10ms p95 สำหรับ header endpoint(s)

**Verify:**
```
cd frontend && npm run build
# manual: open localhost:3000, ดู Network tab ใน DevTools
docker compose logs api --tail=50 | grep "GET /api/" # check req rate
```

**Performance answer (short):** 1 req/วิ ไม่มีปัญหาถ้าเป็น single-row latest queries (account-snapshots, ea-status, market-tick latest = ~1ms/แต่ละ query). ปัญหาจะเกิดถ้ายิง `/api/trade-advisor` ทุกวิ เพราะมัน aggregate basket + pnl_summary หลาย query. **คำแนะนำ: ทำ /api/header-snapshot เฉพาะกิจ + ปล่อย advisor เป็น 30s ตามเดิม.**

---

### TASK: ~~OpenPositions + BasketExitPlan cards equal height~~ DONE

**assignee:** claude
**priority:** normal
**status:** done

**Why:** ใน Real Trading row (col-7 + col-5) card ซ้าย OpenPositions เตี้ยกว่า BasketExitPlan มาก (เพราะมี order เดียว) ทำให้พื้นที่ว่างเสียเปล่า อยากให้สูงเท่ากัน — ปกติ grid-cell จะ stretch อยู่แล้ว แต่ inner card ไม่ `h-full`

**Files to touch:**
- `frontend/src/components/OpenPositions.jsx` — outer `div.bg-gray-900 rounded-lg p-4` → add `h-full`
- `frontend/src/components/BasketExitPlan.jsx` — outer flat container → add `h-full`
- (อาจจะ) `frontend/src/App.jsx` — verify grid items stretch

**Acceptance criteria:**
- [ ] OpenPositions card สูงเท่า BasketExitPlan card ใน lg≥1024px
- [ ] OpenPositions ที่ว่างเยอะ (1 order) ยังดูสะอาด ไม่มี orphan padding มหาศาล — table wrapper อยู่ติดบน, "No data" state ถ้ามีก็ center
- [ ] Stack 1-col ที่ <1024px ยัง work (auto-height ตาม content)

**Verify:**
```
cd frontend && npm run build
# manual: open localhost:3000, real trading row should have aligned cards
```

---

<!-- [BUG] Paper trades open without paper_trader_rule_id: shipped 2026-05-27 — root cause baseline_runner.open_baseline_trade only set rule_id in recovery_plan dict, not column; fix sets paper_trader_rule_id=rule.id; migration 021 backfills orphan independent rows from recovery_plan; mirror exempt by design; 361/361 tests pass. -->

---

<!-- [BUG] Cum PnL stuck at +฿0: shipped 2026-05-26 — cum_pnl_realized field derived from SUM(profit), close flow updates virtual_balance_current. Archived. -->

<!-- 3 codex backlog tasks shipped 2026-05-26: migration 019 (legacy exit_strategy), test_market_tick integration test, migration 020 (NOT NULL filters/gate_status). Archived to task-done.md. -->

<!-- Paper Trade Console — show richer per-rule context: shipped 2026-05-26 as Paper Rule Drawer (12 commits e28b307..9b4b264, 337/337 tests). Archived to task-done.md. -->

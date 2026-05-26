# Paper Rule Drawer — Design Spec

**Date:** 2026-05-26
**Status:** Approved
**Backlog ref:** `Paper Trade Console — show richer per-rule context`

## Problem

`PaperRuleCard` ปัจจุบันแสดงแค่ mode / tier / Net EV / Wilson / vs Baseline / trades / wins. User ดูแล้วบอกไม่ได้ว่ารูล "alive อยู่ไหม", "ทำเงินไหม", "ทำไมไม่ trade", "shadow ดีกว่าหรือเปล่า". ต้องเปิดหลาย tab + curl API จึงจะรู้สถานะจริง.

## Goal

ขยาย `PaperRuleCard` เป็น **collapsed summary + click-to-expand drawer** ที่รวบทุก context ของรูลเดียวไว้ในที่เดียว — โดย reuse endpoints ที่มีอยู่ทั้งหมด เพิ่ม backend field น้อยที่สุดเท่าที่จำเป็น.

## Architecture

```
PaperTradeConsole (polls /api/paper-trader-rules every 5s)
└── PaperRuleCard (collapsed)            ← list item
    └── PaperRuleDrawer (mounted on click; manual refresh only)
        ├── /api/paper-trades?rule_id=...        — active + closed
        ├── /api/paper-signals?rule_id=&limit=20 — signal trail
        ├── /api/paper-trader-rules/{id}/shadows  — parent + shadows + delta
        └── /api/patterns/{pattern_id}/gates      — promotion gates
```

**Data freshness rules**
- Collapsed list (PaperTradeConsole): poll every 5s (existing behavior).
- Drawer: fetch on open, manual refresh button only (no auto-poll while open).
- Each drawer endpoint cached under React Query key `[..., ruleId]` so opening another rule doesn't refetch the first.

## Backend changes

### 1. Extend `PaperTraderRuleResponse` (api/schemas/pattern.py)

Add 4 fields to existing schema:

| field | type | derivation |
|---|---|---|
| `virtual_balance_start` | `Decimal` | direct from ORM |
| `virtual_balance_current` | `Decimal` | direct from ORM |
| `open_trades_count` | `int` | `COUNT(trades WHERE is_paper AND close_time IS NULL AND recovery_plan->>'paper_trader_rule_id' = rule.id::text)` |
| `last_activity_at` | `datetime \| None` | `MAX(emitted_at)` from `paper_signals WHERE rule_id = rule.id` |

`virtual_balance_*` columns already exist in DB (migration 011). The other two are computed in `list_paper_trader_rules` at query time.

### 2. `list_paper_trader_rules` updates (api/routers/patterns.py)

Replace the current per-rule loop with a single batched query:
- One subquery for `open_trades_count` per rule via `recovery_plan->>'paper_trader_rule_id'` group-by
- One subquery for `last_activity_at` from `paper_signals` group-by `rule_id`
- Join both into the response builder

This avoids N+1 calls when 20+ rules are listed.

### 3. `/api/paper-signals` already supports `rule_id` + `limit` — no change needed.

### 4. `/api/paper-trades` already supports `rule_id` — no change needed.

### 5. `/api/paper-trader-rules/{id}/shadows` already returns `parent + shadows + winrate_delta` — no change needed.

### 6. `/api/patterns/{pattern_id}/gates` already returns `gates + reason + tier` per rule — no change needed.

## Frontend changes

### Card states

**Collapsed (`PaperRuleCard.jsx`):**

```
┌─────────────────────────────────────────────────┐
│ ● strict   [3m]              [validated]   ▾   │
│ rsi_14 + ema_50                                 │
│ ─────────────────────────────────────────────── │
│ Open: 2    Balance: ฿4,820 / ฿5,000             │
│ Cum PnL: +฿1,240 (+24.8%)                       │
└─────────────────────────────────────────────────┘
```

- Alive dot from `last_signal_status` + `last_activity_at`:
  - 🟢 `active` (status=active OR last_activity within 5m)
  - 🟡 `near` (status=near)
  - ⚫ `idle` (no activity > 30m or status=idle/far)
- Cum PnL color: green if > 0, red if < 0
- Balance shown red if `virtual_balance_current < virtual_balance_start`
- Shadow rules NOT rendered as cards (kept hidden, surfaced inside parent's drawer)

**Expanded (`PaperRuleDrawer.jsx`):** same header + 6 sections in this order:

1. **Signal Trail** — last 20 paper_signals as colored dots (active/near/far/idle), latest match_pct + missing_conditions
2. **Active Orders** — open trades scoped to this rule_id (ticket, direction, open time/price, unrealized PnL)
3. **Recent History** — closed trades (latest first, 20 visible, scrollable to load more)
4. **Pattern Conditions** — indicator_slugs, timeframe, filters, score_weights
5. **Promotion Gates** — 4-gate breakdown + current trust_tier + gate reason
6. **Shadows** — list of shadow rules with parent vs shadow winrate + delta + filter clause

### React Query keys

```
['paper-rules']                              # list, polled 5s
['paper-trades', ruleId]                     # drawer open
['paper-signals', ruleId]                    # drawer open
['paper-rule-shadows', ruleId]               # drawer open
['paper-rule-gates', patternId]              # drawer open
```

Drawer queries are `enabled: isOpen` so they don't fire until click.

## File changes

| File | Action |
|---|---|
| `api/schemas/pattern.py` | Add 4 fields to `PaperTraderRuleResponse` |
| `api/routers/patterns.py` | Compute `open_trades_count` + `last_activity_at` in `list_paper_trader_rules` |
| `frontend/src/components/PaperRuleCard.jsx` | Rewrite collapsed layout, add expand state + caret |
| `frontend/src/components/PaperRuleDrawer.jsx` | New — 6 sections + manual refresh |
| `frontend/src/components/PaperRuleDrawer/SignalTrail.jsx` | New |
| `frontend/src/components/PaperRuleDrawer/OrdersTable.jsx` | New (handles active + history with scroll) |
| `frontend/src/components/PaperRuleDrawer/PatternConditions.jsx` | New |
| `frontend/src/components/PaperRuleDrawer/PromotionGates.jsx` | New |
| `frontend/src/components/PaperRuleDrawer/ShadowsList.jsx` | New |
| `frontend/src/hooks/usePaperRuleDetail.js` | New — wraps the 4 drawer queries |
| `tests/test_paper_trader_rules_extended.py` | New — covers `open_trades_count` + `last_activity_at` derivation |

Existing `PaperTradeConsole.jsx` stays as-is (already filters out shadows and renders cards). Polling unchanged.

## Testing

**Backend** (TDD per task):
- `open_trades_count`: 0 when no open trades, N when N exist matching rule_id, 0 for closed-only
- `last_activity_at`: NULL when no signals, latest emitted_at otherwise
- `list_paper_trader_rules` does not regress on existing fields
- N+1 prevention: assert query count is bounded (≤ 3) regardless of rule count

**Frontend:**
- Card collapsed renders 4 new fields; alive dot color matches status
- Expand caret toggles drawer; drawer queries `enabled` flag works (no fetch when closed)
- Manual refresh button calls `refetchAll()` for the 4 drawer queries
- Each section renders correctly when data is empty (no shadows, no signals, no closed trades)

## Out of scope

- WebSocket / SSE push for live drawer updates (manual refresh is enough)
- Inline editing of filters or score_weights
- Promoting/demoting rules from UI
- Per-trade drill-down into indicator values at entry time
- Migration of `paper_signals` to a faster store

## Acceptance criteria

- [ ] เปิดหน้า Paper Trade Console แล้ว card ทุกใบมี balance + cum PnL + open count + alive dot
- [ ] คลิก ▾ บนการ์ด → drawer ขยายแสดง 6 sections ครบ (skip ส่วนที่ไม่มีข้อมูลได้)
- [ ] กด ⟳ refresh ใน drawer แล้วทั้ง 4 endpoints ถูก refetch (ดูใน Network tab)
- [ ] Shadow rules ไม่ปรากฏเป็น card หลัก แต่อยู่ใน drawer ของ parent
- [ ] Backend: pytest ผ่านทุก suite รวม regression
- [ ] Network: list endpoint poll 5s ไม่ pile up; drawer queries fire เฉพาะตอน expand

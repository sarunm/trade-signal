# Dashboard Re-design — Command Center Grid

**Date:** 2026-05-26
**Status:** Spec — pending user review
**Related:** `frontend/src/App.jsx`, all `frontend/src/components/*.jsx`

## Goal

Replace the current vertical stack of 8 sections with a Command Center Grid layout that lets the trader see open positions, basket exit plan, alerts, fib levels, and paper lab activity simultaneously without scrolling. Apply a consistent visual language (Modern Indigo palette).

## Why

The current dashboard is a single-column stack: AccountBar → TraderProfile → DailyPL → 3-col Alerts/Insights/Fib → OpenPositions → ClosedTrades → PnlChart → PaperTradeConsole → TradeAdvisor. Trade Advisor — which is the per-trade decision aid — sits at the bottom, far from Open Positions. Daily P/L sits at the top despite being historical review data. The user trades by holding multiple orders at once (แก้ไม้); the current per-trade Trade Advisor does not show the basket-level exit picture, the headroom before margin call, or the realized PnL summary at a glance.

## Decisions (locked during brainstorm)

| Decision | Choice |
|---|---|
| Layout direction | Command Center Grid (12-col + sticky bar) |
| Sticky bar contents | Account + Today PnL + Float PnL + XAUUSD price + Alerts badge + EA status |
| Real vs Paper separation | Visual divider only (heading + thin line) |
| Density | Comfortable (existing `p-4`, `text-sm`) — no compaction |
| Mobile / narrow viewport | Stack to 1 col at `<lg` (1024px); use Tailwind responsive classes |
| Component scope | Keep all 8 existing components; layout-only refactor + targeted enhancements |
| Layout variant | A — Real-First (Real → Paper → History) |
| Color palette | A — Modern Indigo (slate base, emerald/rose accents, indigo brand) |

## Visual Language — Modern Indigo

All color tokens go in `tailwind.config.js` under `theme.extend.colors` so components reference semantic names, not hex.

### Surface colors

| Token | Hex | Tailwind | Use |
|---|---|---|---|
| `bg-base` | `#020617` | `slate-950` | Page background |
| `bg-surface` | `#0f172a` | `slate-900` | Sticky bar, section background |
| `bg-card` | `#1e293b` | `slate-800` | Card / panel background |
| `border-default` | `#334155` | `slate-700` | All borders |
| `text-primary` | `#f1f5f9` | `slate-100` | Main text |
| `text-dim` | `#94a3b8` | `slate-400` | Secondary text, labels |

### Accent colors

| Token | Hex | Tailwind | Use |
|---|---|---|---|
| `profit` | `#34d399` | `emerald-400` | Positive PnL, good entry, alive dot active |
| `loss` | `#fb7185` | `rose-400` | Negative PnL, high-risk verdict |
| `neutral` | `#38bdf8` | `sky-400` | Live price, neutral data |
| `warning` | `#fbbf24` | `amber-400` | Caution verdict, warnings, ruin tier 2 |
| `brand` | `#6366f1` | `indigo-500` | Active filter, primary buttons, focus rings |

### Score chip colors (for OpenPositions score chip)

| Score | Background | Border | Text |
|---|---|---|---|
| ≥ 7.0 | `rgba(52,211,153,0.15)` | `rgba(52,211,153,0.3)` | `emerald-400` |
| 4.0–6.9 | `rgba(251,191,36,0.15)` | `rgba(251,191,36,0.3)` | `amber-400` |
| < 4.0 | `rgba(251,113,133,0.15)` | `rgba(251,113,133,0.3)` | `rose-400` |

## Architecture

```
┌─ <App> ──────────────────────────────────────────────┐
│  <TopBar />              ← sticky, h-14, z-50         │
│  <SectionDivider label="Real Trading" />              │
│  <RealSection />         ← grid-cols-12               │
│  <SectionDivider label="Paper Lab" />                 │
│  <PaperSection />        ← grid-cols-12               │
│  <SectionDivider label="History" />                   │
│  <HistorySection />      ← grid-cols-12               │
│  <PnlHistoryModal />     ← portal, opens from basket  │
└──────────────────────────────────────────────────────┘
```

`<RealSection />`, `<PaperSection />`, `<HistorySection />` are thin layout wrappers; they receive data via existing `usePolling` hooks and render the cards inside their grid columns. Existing data flow (custom polling hooks → fetch JSON → pass props) is unchanged.

## Layout per Section

### Sticky TopBar (h-14)

```
┌─────────────────────────────────────────────────────────────────┐
│ ฿100,250  +฿1,250 (+1.3%)  Float: +฿340     XAUUSD 1958.20      │
│                                              🔔 2  EA●  ⚙        │
└─────────────────────────────────────────────────────────────────┘
```

- Left: Equity, Today PnL (signed + %), Float PL
- Center: XAUUSD live price (mono font, sky-400)
- Right: Alerts count badge (rose), EA status dot, settings gear
- `position: sticky; top: 0; z-50`; shadow appears once page scrolls
- Click alerts badge → smooth scroll to AlertsPanel

Replaces current `<AccountBar />` and `<EAStatusBadge />`. Balance / Margin / Free Margin / Margin Level move into Trader Profile (Section 4).

### Real Trading Section

```
─── REAL TRADING ───────────────────────────────────────

Row 1 (lg:grid-cols-12):
  Open Positions       (col-span-7)
  Basket Exit Plan     (col-span-5)

Row 2 (lg:grid-cols-12):
  Alerts (col-4) | Insights (col-4) | Fib (col-4)
```

**Open Positions** — keep existing component, add a score chip below each row:

```
┌─ XAU BUY 0.10 @ 1955.20 ─────── +฿820 ─┐
│ SL: 1948.00      TP: 1968.00            │
│ ────────────────────────────────────── │
│ [● 7.2 Good entry]                      │ ← chip
└────────────────────────────────────────┘
```

Chip color from score: ≥7.0 emerald, 4.0–6.9 amber, <4.0 rose. Score and verdict come from the existing `entry_score` / `entry_verdict` fields on the trade record (already populated by `services/trade_advisor.py`).

**Basket Exit Plan** — new behavior in the existing `<TradeAdvisor />` component. Replaces per-trade cards with a single basket-level view:

```
─── BASKET EXIT PLAN ─────────────────────────
Net direction: BUY  (0.30 lot, 3 orders)
Avg entry: 1956.40         Current: 1958.20  ↑
Basket BE: 1956.85         Net float: +฿1,040

┌─ PnL SUMMARY ───────────── click to drill ─┐
│ Today        This week     This month       │
│ +฿420        +฿1,850       +฿4,230          │
│ (+0.4%)      (+1.85%)      (+4.23%)         │
└─────────────────────────────────────────────┘

⚠️ RUIN ZONE
  Stop-out price:  1925.40
  Safety margin:  -328 pts  (-฿9,840)
  Buffer: 96.6%  🟢

TP Targets (close basket)
  R2  1972.50    +฿4,690
  R1  1965.10    +฿2,475   ← primary target
  BE  1956.85    +฿0

Add Zones
  S1  1948.30    -฿2,430
  S2  1940.10    -฿4,890

Cut basket if S3 breached: 1928.50  -฿8,355
```

**PnL Summary box** is clickable (`cursor-pointer`, `hover:ring-1 hover:ring-indigo-500`) — opens `<PnlHistoryModal />`.

**Mobile**: stacks Open Positions → Basket Exit Plan → Alerts → Insights → Fib.

### Paper Lab Section

```
─── PAPER LAB ─────────────────────────────────

Header strip:
  5 active rules · Today: +฿420 · Week: +฿1,850
  [all] [ea_cand] [live] [valid] [exp]

Rule cards (lg:3 / md:2 / sm:1):
  ┌ rsi+ema ┐  ┌ basket_5k ┐  ┌ macd_div ┐
  └─────────┘  └───────────┘  └──────────┘
```

- Header strip is new: active count + today PnL + week PnL + filter buttons
- Rule cards (`<PaperRuleCard />`) and drawer (`<PaperRuleDrawer />`) — unchanged from the recent Paper Rule Drawer ship
- Active filter button uses `bg-brand text-white`; inactive uses `bg-card text-dim`

### History Section

```
─── HISTORY ──────────────────────────────────

Row 1 (lg:grid-cols-12):
  Closed Trades     (col-span-7)
  PnL Chart         (col-span-5)

Row 2 (full width):
  Trader Profile
    ├ Account Detail (Balance / Margin / Free / Margin Level)
    └ Behavioral Stats (existing content)
```

`<TraderProfile />` gains a new "Account Detail" sub-block at the top, fed by the existing `/api/account` data. This is where Balance / Margin / Free Margin / Margin Level live (moved out of the sticky bar to keep the bar at h-14).

### PnL History Modal

```
┌── PnL History ──────────────────────────────  [×] ─┐
│                                                    │
│ [ All ] [ Daily ] [ Weekly ] [ Monthly ]           │
│   ↑ active                                         │
│                                                    │
│ ┌──────────┬──────────┬──────────┬─────────┐       │
│ │ Period   │  P/L     │  %       │ Trades  │       │
│ ├──────────┼──────────┼──────────┼─────────┤       │
│ │ 26 May   │ +฿420    │ +0.42%   │   3     │       │
│ │ 25 May   │ +฿890    │ +0.89%   │   5     │       │
│ │ 24 May   │ -฿120    │ -0.12%   │   2     │       │
│ │ ...                                       │       │
│ └────────────────────────────────────────────┘     │
│                                                    │
│            ◀ Prev   Page 1 / 4   Next ▶            │
└────────────────────────────────────────────────────┘
```

- Trigger: click PnL Summary box in Basket Exit Plan
- Default tab: **Daily**
- Tabs: `All` (every closed trade, newest first), `Daily` (group by date), `Weekly` (ISO week), `Monthly` (year-month)
- Pagination: 20 rows per page, `Prev / Page X of N / Next` controls
- Close: ESC, click backdrop, or × button
- Header sticky inside modal scroll area
- Body uses `bg-surface`, table rows alternate with `bg-card` for readability

## Component Inventory

### New (3 files)

| Component | Purpose |
|---|---|
| `frontend/src/components/TopBar.jsx` | Sticky h-14 strip with all the items above |
| `frontend/src/components/SectionDivider.jsx` | `─── LABEL ───` heading + thin line; reused 3 times |
| `frontend/src/components/PnlHistoryModal.jsx` | Tabbed modal with pagination |

### Modified (5 files)

| Component | Change |
|---|---|
| `frontend/src/App.jsx` | Replace stack with TopBar + 3 SectionDividers + 3 grid sections |
| `frontend/src/components/TradeAdvisor.jsx` | Refactor to "Basket Exit Plan" — basket aggregation, Ruin Zone, PnL Summary box |
| `frontend/src/components/TraderProfile.jsx` | Add Account Detail sub-block at top |
| `frontend/src/components/OpenPositions.jsx` | Append score chip below each trade row |
| `frontend/src/components/PaperTradeConsole.jsx` | Add header strip with active count + today/week PnL + filter buttons |

### Deleted (3 files)

| Component | Reason |
|---|---|
| `frontend/src/components/AccountBar.jsx` | Replaced by TopBar |
| `frontend/src/components/EAStatusBadge.jsx` | Folded into TopBar |
| `frontend/src/components/DailyPLPanel.jsx` | Replaced by PnlHistoryModal |

### Untouched

`AlertsPanel`, `ClosedTrades`, `FibPanel`, `InsightsPanel`, `PnlChart`, `PaperRuleCard`, `PaperRuleDrawer`, `SetupTag`, `TrustTierBadge`, `drawer/*`

## Backend Changes

### New endpoint

```
GET /api/pnl-history?granularity={all|daily|weekly|monthly}&page=1&page_size=20

Response:
{
  "items": [
    { "period": "2026-05-26", "profit": 420.00, "profit_pct": 0.42, "trade_count": 3 },
    ...
  ],
  "page": 1,
  "page_size": 20,
  "total_pages": 4,
  "total_count": 78
}
```

- `daily`: same logic as current `/api/daily-pl` plus pagination
- `weekly`: `date_trunc('week', open_time AT TIME ZONE 'Asia/Bangkok')`, period = ISO week start date
- `monthly`: `date_trunc('month', open_time AT TIME ZONE 'Asia/Bangkok')`, period = first-of-month
- `all`: every closed trade (no group), `period` = trade `close_time` ISO string, `trade_count` = 1
- Default `page_size` 20, max 100; `page` is 1-indexed; out-of-range returns empty `items`

### Modified endpoints

```
GET /api/trade-advisor → response gains a `basket` field:

{
  "per_trade": [...],         // existing per-trade data
  "basket": {
    "direction": "buy",        // "buy" | "sell" | "flat"
    "lot_total": 0.30,
    "order_count": 3,
    "avg_entry": 1956.40,
    "current": 1958.20,
    "basket_be": 1956.85,
    "net_float": 1040.00,
    "ruin": {
      "price": 1925.40,
      "pts": -328,
      "baht_buffer": -9840.00,
      "pct_buffer": 96.6,
      "tier": "safe"           // "safe" | "warning" | "danger"
    },
    "tp_targets": [
      { "label": "R2", "price": 1972.50, "baht": 4690.00 },
      { "label": "R1", "price": 1965.10, "baht": 2475.00 },
      { "label": "BE", "price": 1956.85, "baht": 0 }
    ],
    "add_zones": [
      { "label": "S1", "price": 1948.30, "baht": -2430.00 },
      { "label": "S2", "price": 1940.10, "baht": -4890.00 }
    ],
    "cut": { "label": "S3", "price": 1928.50, "baht": -8355.00 },
    "pnl_summary": {
      "today":   { "baht": 420.00,  "pct": 0.42 },
      "week":    { "baht": 1850.00, "pct": 1.85 },
      "month":   { "baht": 4230.00, "pct": 4.23 }
    }
  }
}
```

If no open trades: `basket.direction = "flat"`, `lot_total = 0`, all numeric fields `null`.

```
GET /api/paper-trader-rules → each rule object gains 2 fields:

{
  ...,
  "paper_pnl_today": 420.00,
  "paper_pnl_week": 1850.00
}
```

Reuse `_realized_pnl_by_rule()` helper from `routers/patterns.py`; add a `since: datetime` parameter that filters by `Trade.close_time >= since`.

### Deprecated

```
GET /api/daily-pl → kept until PnlHistoryModal is shipped, then deleted.
```

## Data Flow

- TopBar reads from `usePolling(/api/account, 3000)` (existing)
- Open Positions, Basket Exit Plan share `usePolling(/api/trade-advisor)` (existing endpoint, augmented response)
- Alerts, Insights, Fib, Closed Trades, PnL Chart, Trader Profile, Paper Lab — all use their existing polling hooks unchanged
- PnlHistoryModal opens with local state in Basket Exit Plan; when open, calls `GET /api/pnl-history` with current tab + page; refetches on tab change or page change
- Filter buttons in Paper Lab control local state; rule list filters client-side from existing `usePaperRules()` data

## Error Handling

- TopBar shows `EA○` (gray) when EA stale, badge shown but EA status falls back to last known
- Basket Exit Plan: if no open trades → render "No open positions" placeholder card; if `/api/trade-advisor` fails → existing error message pattern (red text)
- PnL Summary box: if any of today/week/month is `null` (no data) → show `—`, do not break layout
- PnlHistoryModal: if `/api/pnl-history` fails → modal stays open with error banner + Retry button; pagination disabled until success
- Score chip: if `entry_score` is `null` → omit chip, do not render gray placeholder

## Testing Strategy

### Backend (pytest)

- `/api/pnl-history`:
  - Each granularity returns correct grouping (3 trades same day → 1 row in `daily`, 1 row in `weekly`)
  - Pagination: `page=1, page_size=2` returns 2 items, `total_pages` correct
  - Empty database returns `{ items: [], total_pages: 0, total_count: 0 }`
  - `granularity=all` returns one row per closed trade
  - Out-of-range page returns empty items
- Basket aggregation in `/api/trade-advisor`:
  - 3 buys → `direction=buy`, `lot_total = sum(volumes)`, `avg_entry = weighted_avg`
  - Mixed buys + sells → net direction by lot, opposite-side trades subtracted
  - No open trades → `direction=flat`, numeric fields `null`
  - Single trade → basket equals that trade
- Ruin Zone:
  - High buffer (equity ≫ margin) → `tier=safe`
  - Buffer in 20–50% range → `tier=warning`
  - Buffer < 20% → `tier=danger`
  - `equity = margin × stop_out_pct` edge case → `pts=0`, `baht_buffer=0`
- Paper rule pnl_today / pnl_week:
  - Closed trade today → counted in both today and week
  - Closed trade 8 days ago → excluded from both
  - Closed trade 3 days ago → counted in week only

### Frontend

- `npm run build` clean
- Manual smoke: dev server → load `localhost:3000` → all 4 sections render → modal opens / paginates / closes via ESC + backdrop + × → resize to <lg → cards stack 1-col → resize back → cards return to grid

## Risk & Rollback

- **Highest-risk change**: refactoring `App.jsx` — a layout error makes the entire dashboard fail. Mitigation: do it in a feature branch, commit per section, smoke-test after each commit.
- **Backend backward compatibility**: `/api/daily-pl` stays in tree until PnlHistoryModal is verified working in production for at least one session, then deleted in a follow-up commit.
- **Rollback**: `git revert` of the layout commit + frontend rebuild. No DB migrations involved.

## Out of Scope

- Live indicator panels / news feed (mentioned during brainstorm — deferred)
- ML-assisted pattern discovery (logged as separate backlog task `Explore ML to assist pattern discovery / signal scoring`, status `needs-design`, priority `low`)
- Mobile-first redesign — current scope is layout-only refactor; mobile gets stack fallback for free
- Theme switcher / light mode — single dark Modern Indigo theme only
- Custom user settings (panel reorder, hidden sections) — all users see the same layout

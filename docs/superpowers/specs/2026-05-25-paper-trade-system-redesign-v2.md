# Paper Trade System Redesign v2 — Design Spec

> 🔒 **FROZEN REVISION — DO NOT EDIT**
> This document is a frozen revision of the design as decided on 2026-05-25.
> Future changes must go in a new spec file (e.g. `2026-XX-XX-paper-trade-system-redesign-v3.md`)
> that supersedes this one. Keep this file as historical record of decisions.

**Date:** 2026-05-25
**Status:** FROZEN (revision 2)
**Supersedes:** `2026-05-25-paper-trade-system-redesign.md` (revision 1)
**Why v2:** v1 didn't model trading cost, used naive winrate (sample-noise vulnerable), had no baseline benchmark, lacked a 3rd variant matching user's real risk tolerance, and exposed no trust signal to the user.

**Depends on:** Phase 2 Indicator Engine (142 indicators), `trade_indicator_signals` table

---

## Why v2

ระบบต้อง **หาเงินได้จริง** — ไม่ใช่แค่ "หา pattern ที่ winrate สูงในอดีต". v1 มี gap 5 จุดที่ทำให้ promoted rule แพ้จริงตอน live:

1. **ไม่ model cost** — XAUUSD spread 30–50 pip + commission กิน rule winrate 60% ที่ paper จนกลายเป็นขาดทุนจริง
2. **Sample noise** — 50 trades winrate 60% มี true CI = 45–75% (กว้างเกิน) → "ผ่าน gate" ≠ "เชื่อถือได้"
3. **ไม่มี baseline** — ไม่รู้ว่าระบบ add alpha จริง vs random luck
4. **Paper risk model harsher กว่า user style จริง 10×** — rule ที่รอด paper budget ฿5,000 อาจ over-strict สำหรับ user ที่ทน drawdown 5,000 pip
5. **User ไม่มีทาง judge signal trust** — broadcast ทุก rule status='active' เหมือนกัน, ไม่มี tier

v2 แก้ทั้ง 5 จุด — ส่วนอื่นคงโครง v1 ไว้

---

## Carry-over from v1 (unchanged)

ส่วนพวกนี้ยังคงเหมือนใน v1, อย่าแก้ — ดู `2026-05-25-paper-trade-system-redesign.md` รายละเอียด:

- **High-level architecture** (4 components: Mirror, Auto Discovery, Adaptive, Promotion)
- **Component 1 — Mirror Paper** (rule-driven exit: tp_pivot/momentum_flip/hard_stop)
- **Component 2 — Mining direction** (basket grouping, anchor at first trade, weight by basket size)
- **Component 3 — Adaptive Tuning** (feature gap → shadow rule → A/B promote)
- **Component 5 — Signal broadcaster + Console UI** (status emit on change only, age chip)
- **Performance constraints** (P1 shared compute cache, P2 fast/slow split, P3 status-change writes, P4 denormalized rule_id, P5 combo size cap)
- **Recovery** (R1 API restart, R2 EA gap → replay TP/SL at level, R3 UI badge, R4 full restart)
- **Build sequence** — adjusted in §"Build sequence v2" below

ทุกการเปลี่ยนแปลงอยู่ในส่วน v2-only ที่ตามมา

---

## v2-only Δ — Cost Model (new component)

### Why
"Paper TP touch ราคา X" ≠ "ผู้เทรดจริงได้ราคา X" — มี spread + commission + slippage. Promoted rule ต้องผ่าน gate ที่ใช้ **net P/L หลัง cost** ไม่ใช่ raw

### Auto-learn from real trades + ticks

**Spread:**
- `/api/market-tick` รับ bid+ask → คำนวณ `spread = ask - bid` ทุก tick
- เก็บ rolling buffer ใน-memory (size=2000) → ใช้ p50 ของช่วงล่าสุด 7 วันเป็น `learned_spread`
- ถ้า sample < 100 → fallback ไป `PAPER_COST_SPREAD_PIP_DEFAULT=30`

**Commission:**
- Query `trades.commission` ของ real trades (`is_paper=false`) ปิดแล้ว 7 วันล่าสุด
- คำนวณ `avg_commission_per_lot = abs(sum(commission)) / sum(volume)`
- ถ้า sample < 10 trades → fallback ไป `PAPER_COST_COMMISSION_PER_LOT_DEFAULT=10` THB

**Slippage:**
- Static estimate: `PAPER_COST_SLIPPAGE_PIP=2` (ไม่ auto-learn — ไม่มี data ของ "ราคาที่ตั้งใจ" vs "ราคาที่ได้จริง")

### Cost API
```python
# api/services/cost_model.py
@dataclass
class TradeCost:
    spread_pip: Decimal       # ทุก trade เสีย spread 1 ครั้ง (round-trip)
    commission_thb: Decimal   # ตาม volume
    slippage_pip: Decimal     # roundtrip x2
    total_thb: Decimal        # รวมเป็น THB หัก จาก profit

async def estimate_cost(session, trade_or_synthetic) -> TradeCost: ...
async def refresh_cost_cache(session) -> None: ...   # cron hourly
def apply_cost(gross_profit, cost) -> Decimal: ...   # gross_profit - cost.total_thb
```

### Storage
ไม่ persist cost ลง trades row — เก็บ snapshot ใน `cost_calibrations` table:

```sql
CREATE TABLE cost_calibrations (
    id UUID PRIMARY KEY,
    learned_spread_pip NUMERIC,
    learned_commission_per_lot_thb NUMERIC,
    sample_count_spread INT,
    sample_count_commission INT,
    calibrated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_cost_calibrations_calibrated ON cost_calibrations(calibrated_at DESC);
```

ทุกครั้งที่ promotion gate / signal broadcaster / console เรียก `estimate_cost()` → อ่าน latest row (cache 5 min in-memory)

### Files
- `api/services/cost_model.py` (new)
- `api/models/cost_calibration.py` (new)
- `api/alembic/versions/015_cost_model.py` (new)
- `api/main.py` — APScheduler hourly job: `refresh_cost_cache()`

---

## v2-only Δ — Variant C (user_style basket)

### Why
User ทน drawdown 5,000 pip ในชีวิตจริง → paper budget ฿5,000 (= 50 pip ที่ 0.10 lot) คือ harsh model ที่ต่างจาก style จริง 10×. Rule ที่รอดบน variant_B อาจ over-restrictive สำหรับ EA ที่จะใช้กับ user style จริง

### 3 variants per combo

| Variant | Mode | Budget | SL | Recovery | Purpose |
|---|---|---|---|---|---|
| `variant_A` | strict | (lot × ATR×2) | yes | none | Conservative bench |
| `variant_B` | basket_5k | ฿5,000 | none | yes | Mid-risk: ลูกค้าทั่วไป |
| `variant_C` | basket_50k | ฿50,000 | none | yes | User-style: ทน drawdown ถึง 5,000 pip |

ทุก combo ที่ผ่าน mining → spawn 3 rules แทน 2 (`mode IN ('strict', 'basket_5k', 'basket_50k')`)

Recovery logic ของ basket_5k vs basket_50k ใช้ algorithm เดียวกัน (จาก v1) ต่างกันที่ `virtual_balance_start` + threshold

### Schema delta
```sql
-- ปรับ default ของ mode column ใน migration 011 (ก่อน apply)
-- หรือถ้าผ่าน 011 แล้ว เพิ่ม value ใน enum:
-- mode IN ('strict', 'basket_5k', 'basket_50k')
```

(ใช้ String column ไม่ใช่ Postgres ENUM — ไม่ต้อง migrate ENUM, แค่อัปเดต validator)

---

## v2-only Δ — Cost-aware Promotion Gates

### Gate 2 (replace v1 raw winrate/PF)

**v1:**
```
winrate ≥ 0.60
profit_factor ≥ 1.5
max_drawdown ≤ ฿2,500
avg_R_multiple ≥ 1.5
```

**v2:**
```
wilson_lower_95 ≥ 0.55                (sample-noise aware)
net_ev_per_trade ≥ ฿20                (หลัง cost)
profit_factor_net ≥ 1.3               (หลัง cost — ลด threshold เพราะ cost-deducted)
max_drawdown ≤ ฿2,500                 (เท่าเดิม)
beats_baseline_winrate_by ≥ 0.05      (ต้อง outperform baseline rule ≥ 5%)
```

`wilson_lower_95(p, n) = (p + z²/2n − z·√((p(1−p) + z²/4n)/n)) / (1 + z²/n)` กับ `z = 1.96`

### Gate 1 — เปลี่ยน sample requirement
- `total_trades ≥ 100` (จาก v1's 50 — เพราะ Wilson noise floor)
- ที่เหลือ (cover 3 sessions, active 30 days) เหมือนเดิม

### Gate 3, 4 — เหมือน v1

### Gate update output
ผ่าน gate 1+2+3+4 → `status='ea_candidate'` + `trust_tier='ea_candidate'`

### Files
- `api/services/promotion_gate.py` (new)
- `api/services/statistics.py` (new) — Wilson CI helper, EV calc

---

## v2-only Δ — Baseline rules

### Why
Rule ผ่าน gate ที่ "winrate 60% absolute" ยังไม่บอกว่า **เพราะระบบดี vs market บังเอิญดี**. Need control group

### Auto-spawn 1 baseline per active period
ทุก discovery cron run → ถ้าไม่มี active baseline → สร้าง 1 ตัว:

```python
baseline_rule = PaperTraderRule(
    pattern_id=baseline_pattern.id,    # special pattern with empty indicator_slugs
    mode="basket_5k",
    status="active",
    is_baseline=True,
    spawn_strategy="random_session_start",   # entry: ทุก session start (London/NY/Asia open)
)
```

### Pattern row สำหรับ baseline
```python
Pattern(
    indicator_slugs=[],       # empty = signal-less
    timeframe="H1",
    win_rate=0.0,            # populated from baseline runs
    sample_count=0,
    status="baseline",       # special status — ไม่อยู่ใน promotion path
)
```

### Entry trigger (baseline)
- เริ่ม trade ที่ session boundary (London 7:00 UTC, NY 13:00 UTC, Asia 22:00 UTC)
- Direction: alternating buy/sell ต่อ session
- Exit: เหมือน basket_5k logic

### Use ใน promotion gate
```python
baseline_winrate = (await get_baseline_winrate(session, days=30))
if rule.winrate - baseline_winrate < 0.05:
    return PromotionResult(passed=False, reason="not_beating_baseline")
```

### Files
- `api/services/baseline_runner.py` (new) — entry trigger ที่ session boundary
- `api/services/baseline_stats.py` (new) — get rolling baseline winrate

---

## v2-only Δ — Trust tier (4-badge UI)

### Tier definition

| Tier | Criteria | Badge | Color |
|---|---|---|---|
| `experimental` | Active < 7 days OR samples < 30 | "🧪 Experimental" | gray |
| `validated` | Gate 1+2 passed (Wilson lower ≥ 0.55, net_ev ≥ ฿20, beats baseline) | "✓ Validated" | blue |
| `live_proven` | Validated + Gate 3 (7 consecutive days passing) | "★ Live Proven" | green |
| `ea_candidate` | All 4 gates passed | "🎯 EA Candidate" | gold |

### Computation
ทุก promotion gate run (daily cron) → set `paper_trader_rules.trust_tier`. UI อ่านตรงๆ ไม่ recompute

### Schema
```sql
ALTER TABLE paper_trader_rules ADD COLUMN trust_tier VARCHAR(20) DEFAULT 'experimental';
ALTER TABLE paper_trader_rules ADD COLUMN is_baseline BOOLEAN DEFAULT false;
ALTER TABLE paper_trader_rules ADD COLUMN spawn_strategy VARCHAR(40);
```

### UI
Card header (จาก v1):
```
┌──────────────────────────────────────────────────────┐
│ {emoji} Pattern {name} — {slugs} [{age}] [{trust}]   │
│ Net EV: ฿{ev}/trade | Wilson: {w_lo}-{w_hi}          │
│ vs Baseline: +{delta}%                               │
│ ...                                                   │
└──────────────────────────────────────────────────────┘
```

Sort default: `trust_tier DESC, net_ev_per_trade DESC` — user เห็น "best signals" บนสุด

Filter chip: `[All] [EA Candidate] [Live Proven] [Validated] [Experimental]`

### Browser notifications (update from v1)
- เลิกแจ้ง `score ≥ 90 AND status = 'near'` (เก่า — เพราะ score ไม่ใช่ trust)
- ใหม่: **เฉพาะ rule trust_tier ∈ ('live_proven', 'ea_candidate')** + status='near' หรือ 'active' → noti
- Reasoning: user ไม่อยาก spam จาก experimental rules

### Files
- `api/services/trust_tier.py` (new) — `compute_trust_tier(rule, gates_result) -> str`
- `frontend/src/components/TrustTierBadge.jsx` (new)

---

## Schema delta (v2)

### Modify `paper_trader_rules`
```sql
-- เพิ่มจากที่ v1 ทำใน migration 011
ALTER TABLE paper_trader_rules ADD COLUMN trust_tier VARCHAR(20) DEFAULT 'experimental';
ALTER TABLE paper_trader_rules ADD COLUMN is_baseline BOOLEAN DEFAULT false;
ALTER TABLE paper_trader_rules ADD COLUMN spawn_strategy VARCHAR(40);
ALTER TABLE paper_trader_rules ADD COLUMN net_ev_per_trade NUMERIC(10, 2);   -- cached for UI
ALTER TABLE paper_trader_rules ADD COLUMN wilson_lower_95 NUMERIC(5, 4);     -- cached for UI
ALTER TABLE paper_trader_rules ADD COLUMN baseline_delta NUMERIC(5, 4);      -- vs baseline
```

### New table `cost_calibrations` (above)

### Patterns table — allow baseline status
```sql
-- status enum extension: existing values + 'baseline'
-- (ใช้ VARCHAR ไม่ใช่ ENUM — ไม่ต้อง migrate ค่า)
```

### Migration mapping
- `015_cost_model.py` — cost_calibrations table
- `016_v2_promotion_columns.py` — trust_tier, is_baseline, spawn_strategy, net_ev_per_trade, wilson_lower_95, baseline_delta

(011 + 014 ยังเหมือน v1; 012 จะใช้สำหรับ Adaptive Tuning ตามแผน v1; 013 ว่าง — สงวนไว้)

---

## Config (v2 additions)

```
# Cost model
PAPER_COST_SPREAD_PIP_DEFAULT=30
PAPER_COST_COMMISSION_PER_LOT_DEFAULT=10
PAPER_COST_SLIPPAGE_PIP=2
COST_LEARN_WINDOW_DAYS=7
COST_REFRESH_INTERVAL_MIN=60          # APScheduler hourly
COST_LEARN_MIN_SAMPLE_SPREAD=100
COST_LEARN_MIN_SAMPLE_COMMISSION=10

# Variant C
PAPER_VIRTUAL_BUDGET_USER_STYLE=50000
PAPER_USER_STYLE_HARD_STOP_PCT=1.0    # 100% of budget = blown

# Promotion gates (v2)
PROMOTION_MIN_TRADES=100              # raised from 50
PROMOTION_MIN_WILSON_LOWER=0.55       # 95% CI lower bound
PROMOTION_MIN_NET_EV_THB=20           # net per trade
PROMOTION_MIN_PROFIT_FACTOR_NET=1.3
PROMOTION_MIN_BASELINE_DELTA=0.05     # outperform baseline by ≥ 5%

# Baseline
BASELINE_ENABLED=1
BASELINE_DIRECTION_STRATEGY=alternating  # alt | random | longonly | shortonly
BASELINE_SESSIONS=London,NY,Asia
```

(เก็บ config v1 ทั้งหมดไว้ — ไม่ลบ)

---

## Performance budget (v2 additions)

| Operation | Budget | Notes |
|---|---|---|
| Cost model refresh (hourly cron) | < 5s | reads ticks + commission |
| Cost lookup (per gate eval) | O(1) | in-memory cache, 5min TTL |
| Wilson + EV compute (per gate eval) | < 1ms | pure arithmetic |
| Baseline runner (per session boundary) | < 100ms | one trade insert |

ส่วนที่เหลือเหมือน v1

---

## Build sequence v2

1. **Migration 011** + **014** — เหมือน v1
2. **Recovery foundation** — เหมือน v1 (Plan 1 ของ v1)
3. **Migration 015 + cost model** — auto-learn spread/commission, cron refresh (Plan A new)
4. **Migration 016 + v2 schema columns** — trust_tier, is_baseline, EV cache, etc. (Plan A new)
5. **Component 1 — Mirror redesign** — เหมือน v1 (Plan 2 ของ v1)
6. **Component 2 — Auto Discovery + Score sizing + 3rd variant (basket_50k)** — v1 + variant C (Plan 3 ของ v1, เพิ่ม variant_C)
7. **Baseline runner + baseline_stats** — Plan B new
8. **Component 5 — Signal Broadcaster + UI + Trust badges** — เหมือน v1 + trust_tier filter/sort (Plan 4 ของ v1, ขยาย)
9. **Component 4 — Promotion Gate v2** — Wilson + EV + baseline outperformance (Plan 5 ของ v1, rewritten)
10. **Component 3 — Adaptive Tuning** — เหมือน v1 (Plan 6 ของ v1)

Plan files:
- `2026-05-25-paper-plan1-foundation.md` (v1 — ยังใช้ได้, no change)
- `2026-05-25-paper-plan2-mirror-redesign.md` (v1 — ยังใช้ได้, no change)
- `2026-05-25-paper-plan3-auto-discovery-v2.md` — เปลี่ยนจาก v1: เพิ่ม variant_C, เพิ่ม cost-aware mining
- `2026-05-25-paper-plan4-cost-model.md` (new) — แทรกเข้ามา
- `2026-05-25-paper-plan5-signal-broadcaster-v2.md` — เพิ่ม trust badges
- `2026-05-25-paper-plan6-baseline.md` (new) — แยก baseline runner ออกจาก promotion
- `2026-05-25-paper-plan7-promotion-gate-v2.md` — Wilson + EV + baseline check
- `2026-05-25-paper-plan8-adaptive-tuning.md` — เหมือน v1's Plan 6

---

## Out of scope (v2)

- Auto-tuning baseline `BASELINE_DIRECTION_STRATEGY` — keep alternating, defer
- News-event filter (NFP, CPI) — defer
- Cross-symbol rules — XAUUSD only
- WebSocket streaming — keep polling

---

## Open questions

(none — confirmed during v2 brainstorming)

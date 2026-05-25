# Paper Trade System Redesign — Design Spec

**Date:** 2026-05-25
**Supersedes:** `2026-05-24-pattern-discovery-auto-paper-trader-design.md` (Phase 3 + Phase 4)
**Depends on:** Phase 2 Indicator Engine (142 indicators), `trade_indicator_signals` table

---

## Why this redesign

ระบบ paper trade ปัจจุบันไม่ตรงกับ trading style ของ user — เลยไม่สามารถใช้สะท้อนระบบจริงเพื่อทำเป็น EA ได้ในอนาคต

User trading style:
- **Entry**: S/R levels + chart patterns (double/triple top/bottom, wedges)
- **Win exit**: ปิดเองตอนชน R/S ฝั่งตรงข้ามไม่ผ่าน (~400 pip / ~฿500–1,000)
- **Loss handling**: วางไม้แก้ที่ S/R เพิ่ม (lot เท่าเดิม) — ไม่ตั้ง SL
- **Basket close**: เมื่อ net positions บวกแล้ว → รวบปิด เริ่มใหม่
- **Risk capacity**: ทนการวิ่งสวน ~10,000 pip ในบัญชีจริง

ระบบเก่าใช้ ATR-based SL + single trade per rule + indicator-consensus entry — ไม่จับ style นี้เลย และ pattern discovery ทำ direction ผิด (mining จาก trade ทุกอันรวมกัน ไม่ใช่ของ user)

---

## High-level architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Real Trade (MT5)                       │
└─────────────────────────────────────────────────────────┘
              │
              ├──→ [1] Mirror Paper (live, exit ต่างจาก user)
              │       เป้าหมาย: วัด "early exit cost"
              │
              ├──→ [2] Auto Discovery (daily cron)
              │       Mining: indicator combos ตอน user ชนะ
              │       → spawn 2 paper variants ต่อ combo
              │           - A: single-trade + SL (strict)
              │           - B: basket recovery + ฿5,000 budget
              │       → score-based lot sizing (0.01–0.10)
              │
              ├──→ [3] Adaptive Tuning (daily cron)
              │       ดู paper ที่แพ้ของแต่ละ pattern
              │       เสนอ filter เพิ่ม → A/B test → apply
              │
              └──→ [4] Promotion Pipeline
                      4 gates → "ready for EA conversion"
                      Signal broadcaster → user dashboard + noti
```

---

## Component 1 — Mirror Paper (rebuild)

### Goal
ทุกครั้งที่ user เปิด real order → spawn 1 paper ที่ entry/lot/direction เดียวกัน แต่ exit ใช้ rule ของระบบ (ไม่ปิดตาม user) → วัดว่า "ถ้าไม่ปิดเอง จะได้/เสียเท่าไหร่"

### Trigger
`trade_logger.py` หลัง upsert real trade ที่ `order_state=filled AND open_price IS NOT NULL AND close_price IS NULL` → spawn mirror paper async

### Exit logic (ใหม่)
ทุก market tick:
1. **Take profit**: ราคาแตะ R1/R2 (buy) หรือ S1/S2 (sell) ของ daily pivot AND momentum indicator (RSI/MACD) แสดง weakening → exit win
2. **Momentum reversal**: momentum indicator พลิกทิศ (e.g. RSI > 70 → < 60 บน buy) → exit
3. **Hard stop**: floating loss ≥ ฿2,500 (50% of mirror budget) → force close

ลบ logic `_average_offset` เก่าใน `mirror_trader.py` ทิ้ง

### Outputs
- `paper_exit_reason`: `tp_pivot` | `momentum_flip` | `hard_stop`
- เก็บ `early_exit_cost` ใน insights = `mirror.profit - real.profit` (ถ้าบวก = user ปิดเร็วเสีย opportunity, ถ้าลบ = user ปิดถูกจังหวะแล้ว)

---

## Component 2 — Auto Discovery + Spawn (rewrite)

### Mining (รื้อ direction)
**เปลี่ยนจาก**: mining จาก trade ทั้งหมด หา combo winrate สูง
**เป็น**: mining จาก **trade ของ user ที่กำไร** (real, profit > 0) หา combo บ่อยที่สุด

```python
# pseudo
winning_user_trades = SELECT * FROM trades
                      WHERE is_paper = false
                        AND profit > 0
                        AND open_time > cutoff
                        AND order_state = 'filled'
                      ORDER BY close_time DESC
                      LIMIT DISCOVERY_WINDOW_TRADES

for trade in winning_user_trades:
    matched_slugs = SELECT indicator_slug FROM trade_indicator_signals
                    WHERE trade_id = trade.id AND matched = true
    for combo in combinations(matched_slugs, size=2..5):
        combo_count[combo] += 1

candidates = [combo for combo, count in combo_count.items()
              if count >= MIN_OCCURRENCE]  # default 5
```

### Spawn (ใหม่ — 2 variants ต่อ combo)
ทุก combo ที่ผ่าน threshold → สร้าง 2 `paper_trader_rule` rows:
- **variant_A** (`mode=strict`): single trade, SL = ATR×2, no recovery
- **variant_B** (`mode=basket`): recovery basket, no SL, virtual budget ฿5,000

ทั้งคู่ใช้ entry trigger เดียวกัน (combo conditions) แต่ exit/risk ต่างกัน → A/B compare

### Sizing — Score-based (ใหม่)

```
score 0–40:  lot 0.01
score 40–70: lot 0.02   ← default ของ user
score 70–90: lot 0.05
score 90+:   lot 0.10
```

Score formula (cold start: uniform 0.02 จนครบ 100 trades):
```
score = w1 * indicator_count_normalized   (จำนวน indicator match: 2→0, 5→1)
      + w2 * pattern_winrate              (winrate ในอดีต: 0–1)
      + w3 * indicator_strength           (avg strength: e.g. RSI distance from 50)
      + w4 * confluence                   (มี S/R + Fib + indicator พร้อมกันไหม: 0–1)
```
weights default: `w1=0.25, w2=0.40, w3=0.20, w4=0.15`

### Basket recovery logic (variant_B)
```
1. Entry signal match → open ไม้แรก (lot ตาม score)
2. ถ้าราคาวิ่งสวน → wait
3. ราคาแตะ S/R ฝั่งสวน → open ไม้แก้ (lot เท่าไม้แรก)
4. ทุก tick เช็ค net basket P/L:
     - ถ้า net ≥ 0 AND ชน R/S ตรงข้ามไม่ผ่าน → close all (basket win)
     - ถ้า floating loss > ฿5,000 → force close all (basket blown)
5. หลังปิด → reset, รอ entry signal ใหม่
```

### Files to touch
- `api/services/pattern_discovery.py` — rewrite mining direction
- `api/services/paper_trader.py` — split entry/exit by `mode`, add basket logic
- `api/services/scoring.py` (new) — score formula + lot mapping
- `api/models/pattern.py` — เพิ่ม `mode` field on `paper_trader_rule`, virtual_balance fields
- `api/alembic/versions/011_*.py` (new) — migration

---

## Component 3 — Adaptive Tuning (new)

### Trigger
Daily cron หลัง pattern discovery

### Algorithm
```
สำหรับแต่ละ active rule ที่มี ≥ 30 trades:
    losing_trades = trades ของ rule นี้ที่ profit < 0
    winning_trades = trades ของ rule นี้ที่ profit > 0

    หา features ที่แยก loss vs win ได้ชัด:
        - session (London/NY/Asia)
        - volatility regime (ATR percentile)
        - day of week
        - hour bucket
        - indicator state อื่นๆ (เช่น RSI > 70 ตอน buy)

    ถ้า feature X มี:
        loss_rate_when_X=true   - loss_rate_when_X=false  > 0.20
    → propose filter: "ห้าม trade ถ้า X=true"
    → สร้าง shadow rule (active=false) ทดลอง 30 วัน
    → ถ้า shadow winrate > original winrate + 5% → promote shadow แทน original
```

### Files to touch
- `api/services/adaptive_tuner.py` (new)
- `api/models/pattern.py` — เพิ่ม `filters JSONB`, `shadow_of_rule_id` fields
- `api/alembic/versions/012_*.py` (new)

---

## Component 4 — Promotion Pipeline (new)

### 4-Gate Promotion Criteria

**Gate 1 — Sample sufficiency**
- `total_trades ≥ 50`
- Active for `≥ 30 days`
- Cover all 3 sessions (≥ 5 trades each in London / NY / Asia)

**Gate 2 — Performance**
- `winrate ≥ 0.60`
- `profit_factor ≥ 1.5` (gross_win / gross_loss)
- `max_drawdown ≤ ฿2,500`
- `avg_R_multiple ≥ 1.5`

**Gate 3 — Stability**
- ≥ 7 consecutive days passing Gate 2
- ถ้า last-14-day winrate ตก > 15% จาก lifetime → reset stable counter

**Gate 4 — Walk-forward validation**
- แบ่ง trades 70/30 (chronological)
- Train on 70% → confirm winrate ≥ 0.60
- Test on 30% → confirm winrate ≥ 0.55 (max 10% drop allowed)

ผ่านครบ 4 gates → set `status='ea_candidate'`, write promotion event

### Files to touch
- `api/services/promotion_gate.py` (new)
- `api/models/pattern.py` — เพิ่ม `gate_status JSONB`, `promoted_at` fields
- `api/routers/patterns.py` — add `GET /api/patterns/{id}/gates` endpoint

---

## Component 5 — Signal Broadcaster + Paper Console UI (new)

### Backend
ทุก market tick (หลัง paper_trader run):
```
สำหรับแต่ละ active rule:
    match_pct = matched_conditions / total_conditions
    if match_pct >= 1.0    → status = 'active' (paper opened)
    elif match_pct >= 0.80 → status = 'near'
    elif match_pct >= 0.50 → status = 'pending'
    else                   → status = 'idle'

ถ้า status เปลี่ยน → emit signal event → store ใน paper_signals table
```

### Frontend — Paper Trade Console (new route `/paper-trades`)
```
┌──────────────────────────────────────────────────────┐
│ Paper Trade Console                                  │
│ Total: N active | Today: ฿X | Lifetime: ฿Y          │
└──────────────────────────────────────────────────────┘

Per-rule card (one card per active paper_trader_rule):
┌──────────────────────────────────────────────────────┐
│ {status_emoji} Pattern {name} — {indicator_slugs}    │
│ Score: {s} | Winrate: {w}% ({n} trades) | {status}  │
│ Virtual: ฿{start} → ฿{current} ({delta})            │
│ Mode: {strict|basket}                                │
│                                                       │
│ Open positions (basket mode):                         │
│  • {direction} {price} @ {lot} | TP/now: {pl}       │
│ Net: ฿{net}                                          │
│                                                       │
│ Promotion: {n}/4 gates passed                         │
│ Conditions match: {matched}/{total}                   │
│ Missing: {missing_conditions}                         │
└──────────────────────────────────────────────────────┘

Sticky badge for promoted rules: "✅ EA candidate — ready"
```

### Browser notifications (Web Notifications API)
- `score ≥ 90 AND status = 'near'` → "Signal {name} — 95% match, missing X"
- `status changed to 'active'` → "Paper {name} opened: {direction} {price}"
- `rule.status changed to 'ea_candidate'` → "🎉 {name} promoted — review for EA"
- `virtual_balance ≤ 0` → "⚠️ Paper {name} blown — reset"

### Files to touch
- `api/services/signal_broadcaster.py` (new)
- `api/models/paper_signal.py` (new)
- `api/routers/paper_signals.py` (new) — `GET /api/paper-signals?status=`
- `api/alembic/versions/013_*.py` (new) — paper_signals table
- `frontend/src/pages/PaperTradeConsole.jsx` (new)
- `frontend/src/components/PaperRuleCard.jsx` (new)
- `frontend/src/hooks/usePaperSignals.js` (new) — polling + browser noti
- `frontend/src/App.jsx` (modify) — add route + nav link

---

## Data model changes

### Modify `paper_trader_rules`
```sql
ALTER TABLE paper_trader_rules ADD COLUMN mode VARCHAR DEFAULT 'strict';  -- 'strict' | 'basket'
ALTER TABLE paper_trader_rules ADD COLUMN virtual_balance_start NUMERIC DEFAULT 5000;
ALTER TABLE paper_trader_rules ADD COLUMN virtual_balance_current NUMERIC DEFAULT 5000;
ALTER TABLE paper_trader_rules ADD COLUMN score_weights JSONB;
ALTER TABLE paper_trader_rules ADD COLUMN filters JSONB DEFAULT '[]';
ALTER TABLE paper_trader_rules ADD COLUMN shadow_of_rule_id UUID NULL;
ALTER TABLE paper_trader_rules ADD COLUMN gate_status JSONB DEFAULT '{}';
ALTER TABLE paper_trader_rules ADD COLUMN promoted_at TIMESTAMPTZ NULL;
ALTER TABLE paper_trader_rules ADD COLUMN consecutive_stable_days INT DEFAULT 0;
```

### New table: `paper_signals`
```sql
CREATE TABLE paper_signals (
    id UUID PRIMARY KEY,
    rule_id UUID REFERENCES paper_trader_rules(id),
    status VARCHAR,                    -- pending | near | active | exited
    match_pct NUMERIC,
    matched_conditions VARCHAR[],
    missing_conditions VARCHAR[],
    score NUMERIC,
    suggested_lot NUMERIC,
    emitted_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_paper_signals_rule_emitted ON paper_signals(rule_id, emitted_at DESC);
```

### New table: `score_calibrations` (for Component 2 self-tuning)
```sql
CREATE TABLE score_calibrations (
    id UUID PRIMARY KEY,
    score_tier VARCHAR,                -- '0-40' | '40-70' | '70-90' | '90+'
    expected_winrate NUMERIC,          -- ที่ระบบคาดการณ์
    actual_winrate NUMERIC,            -- ที่เกิดจริง
    sample_count INT,
    calibrated_at TIMESTAMPTZ DEFAULT now()
);
```

---

## Config (env vars)

```
DISCOVERY_WINDOW_TRADES=50
DISCOVERY_WINDOW_MAX_DAYS=30
DISCOVERY_MIN_OCCURRENCE=5
PAPER_VIRTUAL_BUDGET=5000
PAPER_HARD_STOP_PCT=1.0          # 100% of budget = blown
SCORE_COLD_START_TRADES=100
SCORE_W_INDICATOR_COUNT=0.25
SCORE_W_PATTERN_WINRATE=0.40
SCORE_W_INDICATOR_STRENGTH=0.20
SCORE_W_CONFLUENCE=0.15
PROMOTION_MIN_TRADES=50
PROMOTION_MIN_DAYS=30
PROMOTION_MIN_WINRATE=0.60
PROMOTION_MIN_PROFIT_FACTOR=1.5
PROMOTION_STABLE_DAYS=7
ADAPTIVE_FILTER_MIN_TRADES=30
ADAPTIVE_LOSS_RATE_GAP=0.20
SIGNAL_NEAR_THRESHOLD=0.80
SIGNAL_PENDING_THRESHOLD=0.50
```

---

## Build sequence

1. **Migration 011** — schema changes (paper_trader_rules + paper_signals + score_calibrations)
2. **Component 1 — Mirror redesign** (small, isolated; ship first to validate exit logic)
3. **Component 2 — Auto Discovery rewrite + Score sizing** (core; depends on 1's exit logic)
4. **Component 5 — Signal Broadcaster + UI** (visible feedback to user; depends on 2)
5. **Component 4 — Promotion Gate** (depends on 2's data accumulation)
6. **Component 3 — Adaptive Tuning** (last; needs ≥ 30 trades per rule)

Each step has its own task in backlog with own tests + acceptance criteria.

---

## Out of scope

- Detecting chart patterns (double top/bottom, wedges) automatically — defer; for now use S/R + indicator combo as proxy
- Generating MQL5 EA code from promoted rules — separate spec later
- News-based filters in Adaptive Tuning — defer
- Real-time price streaming via WebSocket — keep polling; tick handler is fast enough

---

## Open questions

(none — confirmed during brainstorming)

# Paper Trade System Redesign — Design Spec

> 🔒 **FROZEN REVISION — DO NOT EDIT**
> This document is a frozen revision of the design as decided on 2026-05-25.
> Future changes must go in a new spec file (e.g. `2026-XX-XX-paper-trade-system-redesign-v2.md`)
> that supersedes this one. Keep this file as historical record of decisions.

**Date:** 2026-05-25
**Status:** FROZEN (revision 1)
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
- **Risk capacity**: ทนการวิ่งสวน > 5,000 pip ในบัญชีจริง

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
**เป็น**: mining จาก **basket ของ user ที่ปิดเป็น net profit** หา combo บ่อยที่สุด

#### Basket grouping
User ปกติเปิดไม้แก้แล้วรวบปิดทีเดียว — ถ้านับแต่ละ trade แยกกัน mining จะเข้าใจผิด เลยต้อง group ก่อน

```python
def group_into_baskets(real_trades, gap_sec=BASKET_CLOSE_GAP_SEC):
    sorted_trades = sorted(real_trades, key=lambda t: t.close_time)
    baskets, current = [], [sorted_trades[0]]
    for t in sorted_trades[1:]:
        if (t.close_time - current[-1].close_time).total_seconds() <= gap_sec:
            current.append(t)
        else:
            baskets.append(current); current = [t]
    baskets.append(current)
    return baskets
```

#### Mining algorithm — anchor ที่ "ไม้แรก", weight ตาม basket size

User insight: basket ใหญ่ = pattern ไม่ดี (ต้องแก้หลายไม้). Basket > 2 ไม้ = abnormal — user เองยังบอกว่าผิดปกติ → ทิ้ง

```python
winning_baskets = [b for b in group_into_baskets(real_trades)
                   if sum(t.profit for t in b) > 0]

for basket in winning_baskets:
    if len(basket) > MINING_MAX_BASKET_SIZE:   # default 2
        continue                                # abnormal — skip

    weight = 1.0 if len(basket) == 1 else 0.7  # size 2 = penalize เล็กน้อย

    first_trade = min(basket, key=lambda t: t.open_time)
    matched_slugs = SELECT indicator_slug FROM trade_indicator_signals
                    WHERE trade_id = first_trade.id AND matched = true
    for combo in combinations(matched_slugs, size=2..MINING_MAX_COMBO_SIZE):
        combo_score[combo] += weight

candidates = [combo for combo, score in combo_score.items()
              if score >= MIN_OCCURRENCE]  # default 5 (ใช้ score ไม่ใช่ count)
```

**ทำไมใช้ไม้แรก:** entry decision ของ pattern อยู่ที่ไม้แรก ไม้แก้คือ recovery (คนละเรื่อง) — pattern ที่อยากเลียนแบบใน EA คือ "เปิดไม้แรกตอนไหนถึงมักจะรอด"

**Basket size 1:** weight = 1.0 (clean signal — เปิดแล้วบวกเลย)
**Basket size 2:** weight = 0.7 (ต้องแก้ 1 ครั้ง — penalize เล็กน้อย)
**Basket size ≥ 3:** ทิ้ง (abnormal เกิน)

### Spawn (ใหม่ — 2 variants ต่อ combo)
ทุก combo ที่ผ่าน threshold → สร้าง 2 `paper_trader_rule` rows:
- **variant_A** (`mode=strict`): single trade, SL = ATR×2, no recovery
- **variant_B** (`mode=basket`): recovery basket, no SL, virtual budget ฿5,000

ทั้งคู่ใช้ entry trigger เดียวกัน (combo conditions) แต่ exit/risk ต่างกัน → A/B compare

### No spawn cap
**ไม่จำกัดจำนวน rules ที่ระบบ spawn ได้** — ยิ่งเยอะยิ่งดี เพราะแต่ละ rule = สถานการณ์จำลองที่ต่างกัน ระบบต้องเก็บข้อมูลให้ได้หลากหลาย combo เพื่อให้ promotion gate (Component 4) มีตัวเลือกพอที่จะคัด "ตัวที่ดีจริง"

Dedup: ถ้า combo ซ้ำกับ rule เดิมที่ active อยู่ → skip (อย่าสร้างซ้ำ) แต่ถ้ายังไม่เคยมี → สร้างเลย ไม่ต้องสนใจว่ามี rule อยู่กี่ตัวแล้ว

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
3. Recovery trigger (อันใดอันหนึ่ง):
     a. PRIMARY: ราคาแตะ S/R ถัดไปฝั่งสวน → open ไม้แก้
     b. FALLBACK: floating loss ≥ 30% ของ virtual budget (฿1,500)
        AND ไม่มีไม้แก้ใหม่ใน 30 นาทีล่าสุด → force open ไม้แก้ที่ราคาปัจจุบัน
   ทุกไม้แก้ใช้ lot เท่าไม้แรก
4. ทุก tick เช็ค net basket P/L:
     - ถ้า net ≥ 0 AND ชน R/S ตรงข้ามไม่ผ่าน → close all (basket win)
     - ถ้า floating loss > ฿5,000 → force close all (basket blown)
5. หลังปิด → reset, รอ entry signal ใหม่
```

**Fallback rationale:** ถ้าระบบรอแต่ S/R และราคา drift ผ่าน level โดยไม่ touch (gap, fast move, S/R ห่างเกิน) basket จะ blown โดยไม่ได้ recover เลย → fallback กัน edge case นี้ คุ้มกว่ารอ "perfect entry" แล้วโดน blown

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
│ {status_emoji} Pattern {name} — {indicator_slugs}  [{age}]│
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

**Age chip ที่ header:**
- แสดง relative age (`3d`, `12h`, `2w`) จาก `paper_trader_rules.spawned_at`
- Tooltip on hover → absolute timestamp (`2026-05-22 14:30 UTC`)
- ใช้ `Intl.RelativeTimeFormat` ฝั่ง frontend ก็พอ ไม่ต้อง backend compute

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
ALTER TABLE paper_trader_rules ADD COLUMN last_signal_status VARCHAR;  -- restart-safe signal state
```

### Modify `trades` (denormalize for performance)
```sql
ALTER TABLE trades ADD COLUMN paper_trader_rule_id UUID NULL;
CREATE INDEX idx_trades_open_paper_rule ON trades(paper_trader_rule_id)
    WHERE close_time IS NULL AND is_paper = true;
```

### New table: `ea_status`
```sql
CREATE TABLE ea_status (
    account_id BIGINT PRIMARY KEY,
    last_seen_at TIMESTAMPTZ NOT NULL,
    version VARCHAR,
    symbol VARCHAR
);
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

-- TimescaleDB hypertable + retention
SELECT create_hypertable('paper_signals', 'emitted_at');
SELECT add_retention_policy('paper_signals', INTERVAL '30 days');
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

## Performance — design constraints

EA ส่ง market-tick ทุก **1 วินาที** + ไม่จำกัด spawn → ต้อง design ให้ scale ได้ถึง 100+ active rules ตั้งแต่ day 1

### P1 — Shared indicator compute cache (ต่อ tick)
**ปัญหา:** Naive loop = O(rules × indicators) → 100 rules × 3 indicators × 20ms = 6 sec/tick → budget แตก

**วิธี:** ทุก tick → compute (slug, timeframe) ครั้งเดียว เก็บใน dict, rule check = O(1) lookup

```python
async def run_paper_trader(session, tick):
    rules = await load_active_rules(session)
    unique_keys = {(slug, rule.timeframe)
                   for rule in rules for slug in rule.indicator_slugs}

    # compute เพียงครั้งเดียวต่อ tick
    bars_cache: dict[str, list[PriceBar]] = {}
    indicator_cache: dict[tuple[str, str], IndicatorResult] = {}
    for slug, tf in unique_keys:
        if tf not in bars_cache:
            bars_cache[tf] = await fetch_bars(session, tick.symbol, tf)
        indicator_cache[(slug, tf)] = compute(slug, bars_cache[tf])

    for rule in rules:
        results = [indicator_cache[(s, rule.timeframe)] for s in rule.indicator_slugs]
        # ... entry/exit logic
```

ลด complexity จาก O(rules × slugs) → O(unique slug-tf combos)

### P2 — Fast/slow tick path split
- **Fast path (every tick, 1s):** TP/SL touch, hard_stop check, basket net P/L → O(open_trades) เท่านั้น ไม่ touch indicators
- **Slow path (every `INDICATOR_COMPUTE_INTERVAL_SEC=15`s, หรือเมื่อ bar close):** indicator compute, signal status emit, entry decision

Indicators เช่น RSI/MACD ไม่เปลี่ยนใน 1 วิ — compute ทุก 15 วิเพียงพอ

### P3 — paper_signals table — write only on status change
**ปัญหา:** ถ้าเขียนทุก tick = 100 rules × 86,400 sec = 8.6M rows/day

**วิธี:**
- เขียน **เฉพาะตอน status เปลี่ยน** (idle ↔ pending ↔ near ↔ active ↔ exited)
- Last status เก็บ in-memory dict + persist ใน `paper_trader_rules.last_signal_status` เพื่อ restart-safe
- TimescaleDB hypertable + retention policy 30 วัน (drop old rows อัตโนมัติ)

### P4 — Denormalize `paper_trader_rule_id` ลง trades
**ปัจจุบัน:** filter open paper trades ผ่าน `recovery_plan->>'paper_trader_rule_id'` (JSONB) → ไม่ใช้ index, scan ทุก row

**วิธี:** เพิ่ม column `trades.paper_trader_rule_id UUID NULL` + index `(paper_trader_rule_id) WHERE close_time IS NULL` → query ลด O(N) → O(log N)

### P5 — Pattern discovery combinatorics
`combinations(2..5)` of 20 matched slugs = 21,679 combos/trade × 50 trades = 1M ops

**วิธี:** จำกัด `MINING_MAX_COMBO_SIZE=4` (ค่า default ใหม่) + pre-filter slugs ที่ปรากฏใน ≥ 3 baskets ก่อน combine

### Performance budget
| Operation | Budget | Notes |
|---|---|---|
| Fast path (tick) | < 50ms | TP/SL/hard_stop only |
| Slow path (15s) | < 2s | indicator compute + signal emit |
| Pattern discovery cron (daily) | < 60s | offline, cron 00:00 UTC |
| Adaptive tuning cron (daily) | < 30s | offline |

---

## Recovery — restart safety

ระบบต้อง survive 3 scenarios: API restart, EA disconnect, full docker compose down

### R1 — API restart (FastAPI ดับ + ขึ้นใหม่)
**State ที่อยู่ใน DB อยู่แล้ว (safe):** active rules, open paper trades, baskets, virtual_balance, win_count

**State in-memory ที่หาย:**
- `_rule_cache` → reload จาก DB on first tick (TTL 1 hr อยู่แล้ว)
- `last_signal_status` per rule → persist ใน column `paper_trader_rules.last_signal_status`
- Recovery cooldown timer (30 min ระหว่างไม้แก้) → **derive จาก `trades.open_time` ของไม้ล่าสุดใน basket** ไม่ต้อง persist

```python
def can_open_recovery(basket_trades, now, cooldown_min=30):
    if not basket_trades:
        return True
    latest = max(t.open_time for t in basket_trades)
    return (now - latest).total_seconds() / 60 >= cooldown_min
```

restart-safe โดย default — ไม่มี state แยกที่ต้อง sync

### R2 — EA disconnect / reconnect (gap)
**Detection:** EA ส่ง heartbeat ที่ `POST /api/ea-heartbeat` ทุก 60s → เก็บ `last_seen_at` ใน table `ea_status`

**Policy: Replay TP/SL ตามราคา reconnect**
ตอน first market-tick หลัง gap (gap > 60s):
1. Detect gap = `now - last_tick_time > 60s`
2. สำหรับทุก open paper trade:
   - ถ้า direction=buy AND `tick.bid >= tp` → close at `tp` (level-based, ไม่ใช่ราคา reconnect)
   - ถ้า direction=buy AND `tick.bid <= sl` → close at `sl`
   - sell ทำ mirror
3. ถ้า level อยู่ระหว่าง gap → assume touched, exit ที่ level นั้น (realistic, ใกล้กับสิ่งที่จะเกิดถ้าระบบไม่หยุด)
4. Log `paper_exit_reason='replayed_after_gap'` เพื่อ audit

**ทำไมเลือกแบบนี้:** force-close ตัด opportunity, ignore gap ทำ P/L เพี้ยน — replay ที่ level ที่ตั้งไว้คือ middle ground

### R3 — UI: EA connection status
- Dashboard header แสดง `🟢 EA connected (last seen: 5s ago)` หรือ `🔴 EA disconnected (3 min)`
- Paper Console banner: `⚠️ EA disconnected — paper trades paused` ถ้า last_seen > 2 min
- ใช้ `last_seen_at` จาก heartbeat — frontend poll `/api/ea-status` ทุก 10s

### R4 — Full docker compose down
ทุก container ดับ → ขึ้นมาใหม่:
- DB ยังอยู่ (volume persist) → state ทั้งหมดยังอยู่
- API restart → R1
- EA reconnect → R2
- ไม่ต้องทำอะไรเพิ่ม

### Files to touch (recovery)
- `api/routers/ea_status.py` (new) — `POST /api/ea-heartbeat`, `GET /api/ea-status`
- `api/models/ea_status.py` (new) — single-row table `(account_id PK, last_seen_at, version)`
- `api/services/paper_trader.py` (modify) — gap detection + replay logic ใน entrypoint
- `ea/TradeSignalBridge.mq5` (modify) — เพิ่ม heartbeat call ทุก 60s
- `frontend/src/components/EAStatusBadge.jsx` (new)
- `frontend/src/hooks/useEAStatus.js` (new)
- `api/alembic/versions/014_*.py` (new) — ea_status table + last_signal_status column

---

## Config (env vars)

```
DISCOVERY_WINDOW_TRADES=50
DISCOVERY_WINDOW_MAX_DAYS=30
DISCOVERY_MIN_OCCURRENCE=5
BASKET_CLOSE_GAP_SEC=1            # close_time ห่างกัน ≤ 1 วิ = basket เดียวกัน
MINING_MAX_BASKET_SIZE=2          # basket > นี้ = abnormal, ทิ้ง
MINING_MAX_COMBO_SIZE=4           # combinations(2..4) — กัน combinatorial explosion
PAPER_VIRTUAL_BUDGET=5000
PAPER_HARD_STOP_PCT=1.0           # 100% of budget = blown
PAPER_RECOVERY_FALLBACK_PCT=0.30  # floating loss ≥ 30% → force recovery
PAPER_RECOVERY_COOLDOWN_MIN=30    # cooldown ระหว่างไม้แก้ (นาที)
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
INDICATOR_COMPUTE_INTERVAL_SEC=15  # slow-path: indicator compute interval
EA_HEARTBEAT_INTERVAL_SEC=60       # EA → API heartbeat
EA_GAP_THRESHOLD_SEC=60            # gap > นี้ → trigger replay
EA_DISCONNECT_UI_THRESHOLD_SEC=120 # banner "EA disconnected"
PAPER_SIGNALS_RETENTION_DAYS=30    # TimescaleDB drop policy
```

---

## Build sequence

1. **Migration 011** — paper_trader_rules + paper_signals + score_calibrations
2. **Migration 014** — ea_status + denormalized columns (trades.paper_trader_rule_id, last_signal_status)
3. **Recovery foundation** (R1+R2+R3) — heartbeat endpoint + EA heartbeat + UI badge — ship early so subsequent components inherit gap-safe behavior
4. **Component 1 — Mirror redesign** (small, isolated; validate exit logic)
5. **Component 2 — Auto Discovery rewrite + Score sizing** (core; ต้องมี shared compute cache ตั้งแต่แรก ห้าม optimize ทีหลัง)
6. **Component 5 — Signal Broadcaster + UI** (status emit เฉพาะ change, age chip, EA status banner)
7. **Component 4 — Promotion Gate** (depends on 2's data accumulation)
8. **Component 3 — Adaptive Tuning** (last; needs ≥ 30 trades per rule)

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

# Pattern Discovery + Auto Paper Trader — Design Spec

**Date:** 2026-05-24  
**Phase 3:** Pattern Discovery Engine  
**Phase 4:** Auto Paper Trader  
**Depends on:** Phase 2 Indicator Engine (Task #5–12) must be complete and accumulating entry-time signals

---

## Overview

ระบบเรียนรู้จาก trade จริงของ user แบบ automated loop:

```
trade จริง → indicator signals (Phase 2)
                    ↓
           Pattern Discovery (Phase 3) — daily cron
           หา combination ของ indicators ที่ correlate กับ winning trades
                    ↓
           Pattern Registry — เก็บ patterns ที่ stable
                    ↓
           Auto Paper Trader (Phase 4) — ทุก 60s
           monitor live prices → entry เมื่อ conditions ครบ → exit แบบ Hybrid
```

ยิ่งเทรดนาน → ข้อมูลเยอะขึ้น → patterns ชัดขึ้น → paper traders แม่นขึ้น

---

## Phase 3 — Pattern Discovery Engine

### Goal

วิเคราะห์ `trade_indicator_signals` (entry-time signals จาก Phase 2) หา combinations ของ indicators ที่มี win rate สูงและ sample พอ แล้ว spawn paper trader rule โดยอัตโนมัติ

### Algorithm (รัน daily cron หลัง market close)

```
1. ดึง trades ที่ปิดแล้ว โดยใช้ window แบบ dual-constraint:
     cutoff_by_count = timestamp ของ trade ที่ปิดล่าสุด DISCOVERY_WINDOW_TRADES ตัว
     cutoff_by_age   = now() - DISCOVERY_WINDOW_MAX_DAYS days
     cutoff = max(cutoff_by_count, cutoff_by_age)  ← เอาที่ recent กว่า (window เล็กกว่า)
   พร้อม indicator signals ของแต่ละตัว
2. สำหรับแต่ละ trade: collect set ของ indicator slugs ที่ matched=True
3. generate combinations ขนาด 2–5 slugs จาก matched slugs ของแต่ละ trade
4. สำหรับแต่ละ combination:
     win_count  = จำนวน trades ที่ combination นี้ matched AND profit > 0
     total      = จำนวน trades ที่ combination นี้ matched (ทั้ง win/loss)
     win_rate   = win_count / total
5. filter: total >= 10 AND win_rate >= 0.60
6. สำหรับแต่ละ combination ที่ผ่าน filter:
     ถ้ายังไม่มีใน patterns table → สร้างใหม่ status=candidate, consecutive_stable_days=1
     ถ้ามีแล้ว status=candidate → consecutive_stable_days += 1
     ถ้า consecutive_stable_days >= 3 → promote เป็น status=active
7. สำหรับ pattern ที่ active ใหม่:
     dedup check กับ paper_trader_rules ที่ active อยู่
     ถ้า Jaccard similarity > 0.8 กับ rule ใด → ถือว่าซ้ำ skip
     ถ้าไม่ซ้ำ → สร้าง paper_trader_rule ใหม่
8. patterns ที่ไม่ผ่าน filter 3 วันติดกัน → reset consecutive_stable_days = 0
9. paper_trader_rules ที่ pattern ถูก retire → อัปเดต status=retired
```

### Stability Thresholds (calibrated สำหรับ 5 trades/day)

| Parameter | Config Key | Default | เหตุผล |
|-----------|-----------|---------|--------|
| min sample | `DISCOVERY_MIN_SAMPLE` | 10 trades | statistical floor ก่อน promote |
| min win rate | `DISCOVERY_MIN_WIN_RATE` | 0.60 | ต้องดีกว่า random |
| window — max trades | `DISCOVERY_WINDOW_TRADES` | 50 | statistical power คงที่ ไม่ขึ้นกับ trading frequency |
| window — max age | `DISCOVERY_WINDOW_MAX_DAYS` | 30 | ป้องกัน pattern เก่าจาก market condition ที่ต่างไป |
| consecutive stable days | `DISCOVERY_STABLE_DAYS` | 3 | ยืนยันว่าไม่ใช่ statistical noise |

Window ใช้ "last 50 trades แต่ไม่เกิน 30 วัน" — whichever is the smaller set:
```python
# api/services/pattern_discovery.py
DISCOVERY_WINDOW_TRADES  = int(os.getenv("DISCOVERY_WINDOW_TRADES", 50))
DISCOVERY_WINDOW_MAX_DAYS = int(os.getenv("DISCOVERY_WINDOW_MAX_DAYS", 30))
DISCOVERY_MIN_SAMPLE     = int(os.getenv("DISCOVERY_MIN_SAMPLE", 10))
DISCOVERY_MIN_WIN_RATE   = float(os.getenv("DISCOVERY_MIN_WIN_RATE", 0.60))
DISCOVERY_STABLE_DAYS    = int(os.getenv("DISCOVERY_STABLE_DAYS", 3))
```

### Deduplication

```python
def jaccard(slugs_a: set, slugs_b: set) -> float:
    return len(slugs_a & slugs_b) / len(slugs_a | slugs_b)

# ถ้า jaccard > 0.8 กับ active rule ใดก็ตาม → ถือว่าซ้ำ
```

### Data Model

**Migration 010 — patterns table**
```sql
CREATE TABLE patterns (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    indicator_slugs       VARCHAR[]    NOT NULL,
    timeframe             VARCHAR      NOT NULL DEFAULT 'H1',
    win_rate              FLOAT        NOT NULL,
    sample_count          INT          NOT NULL,
    consecutive_stable_days INT        NOT NULL DEFAULT 0,
    status                VARCHAR      NOT NULL DEFAULT 'candidate',
    -- status: candidate | active | retired
    discovered_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    promoted_at           TIMESTAMPTZ
);
```

**Migration 010 — paper_trader_rules table**
```sql
CREATE TABLE paper_trader_rules (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_id  UUID         NOT NULL REFERENCES patterns(id),
    status      VARCHAR      NOT NULL DEFAULT 'active',
    -- status: active | paused | retired
    spawned_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    total_trades INT         NOT NULL DEFAULT 0,
    win_count    INT         NOT NULL DEFAULT 0
);
```

### Files to Create/Modify

```
api/alembic/versions/010_add_patterns.py          New — migration
api/models/pattern.py                             New — Pattern, PaperTraderRule ORM
api/schemas/pattern.py                            New — Pydantic schemas
api/services/pattern_discovery.py                 New — discovery algorithm
api/routers/patterns.py                           New — GET /api/patterns, /api/paper-trader-rules
api/main.py                                       Modify — register router + schedule cron
tests/test_pattern_discovery.py                   New
```

### Cron Scheduling

ใช้ `APScheduler` (เพิ่มใน requirements.txt) รัน `run_pattern_discovery()` ทุกวันตอน 00:00 UTC:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()
scheduler.add_job(run_pattern_discovery, "cron", hour=0, minute=0)
scheduler.start()  # ใน FastAPI lifespan
```

### API Endpoints

```
GET /api/patterns
  → list ของ patterns ทั้งหมด (filter by status optional)
  → fields: id, indicator_slugs, win_rate, sample_count, status, promoted_at

GET /api/paper-trader-rules
  → list ของ active paper trader rules
  → fields: id, pattern_id, status, spawned_at, total_trades, win_count, derived win_rate
```

### Acceptance Criteria

- [ ] Migration 010 สร้าง `patterns` และ `paper_trader_rules` tables ถูกต้อง
- [ ] `run_pattern_discovery()` วิเคราะห์ 14-day window และ upsert patterns ถูกต้อง
- [ ] combination ที่ sample < 10 หรือ win_rate < 60% ไม่ถูก promote
- [ ] `consecutive_stable_days` เพิ่มขึ้นทุกวันที่ผ่าน threshold, reset เมื่อไม่ผ่าน
- [ ] pattern ที่ stable 3 วัน → สร้าง paper_trader_rule ถ้า Jaccard < 0.8 กับทุก active rule
- [ ] `GET /api/patterns` และ `GET /api/paper-trader-rules` คืนข้อมูลถูกต้อง
- [ ] APScheduler รัน discovery ทุกวัน (unit test: call function โดยตรง)
- [ ] pytest ผ่านทุก test รวม regression

---

## Phase 4 — Auto Paper Trader

### Goal

Monitor live prices ทุก 60 วินาที ตรวจสอบว่า indicator conditions ของ active paper_trader_rules ครบมั้ย ถ้าครบ → auto entry paper trade และ exit ด้วย Hybrid strategy

### Exit Strategy — Hybrid C

| Priority | เงื่อนไข | Action |
|----------|---------|--------|
| 1 | price ≥ TP (S/R level) | close, win |
| 2 | price ≤ SL (ATR stop) | close, loss |
| 3 | momentum indicator ใน rule พลิก direction | close, early exit |

ลำดับ 1-2 เช็คก่อนเสมอ (O(1) comparison) — momentum เช็คสุดท้าย (ต้อง compute indicator)

### Architecture

```
POST /api/market-tick (ทุก 60s จาก EA)
        │
        ├── [เดิม] บันทึก price bar, account snapshot
        │
        └── asyncio.create_task(_run_paper_trader())
                    │
                    ├── load_active_rules()     ← จาก in-memory cache
                    ├── fetch_bars()            ← query price_bars ครั้งเดียว
                    ├── _check_entries()        ← Signal Monitor
                    └── _check_exits()          ← Exit Manager
```

### In-Memory Cache (performance)

```python
# api/services/paper_trader.py
_rule_cache: list[PaperTraderRule] = []
_cache_refreshed_at: datetime | None = None
CACHE_TTL_SECONDS = 3600  # refresh ทุก 1 ชั่วโมง

async def load_active_rules(session) -> list[PaperTraderRule]:
    if cache ยัง valid → return _rule_cache
    # query DB เฉพาะเมื่อ cache expired
    _rule_cache = await session.execute(select(PaperTraderRule).where(status="active"))
    _cache_refreshed_at = datetime.utcnow()
    return _rule_cache
```

### Signal Monitor (Entry)

```
1. load active rules from cache
2. collect unique slugs จากทุก rules → needed_slugs
3. fetch latest bars ต่อ timeframe ที่ต้องการ (1 query ต่อ TF)
4. สำหรับแต่ละ rule:
     compute indicators ใน rule.indicator_slugs เท่านั้น (ไม่ใช่ทั้ง 142)
     ถ้า ALL indicators matched:
         เช็คว่ามี open paper trade ของ rule นี้อยู่มั้ย
         ถ้าไม่มี:
             TP = nearest S/R level จาก pivot/fib indicators
             SL = current_price ± ATR(14) × 1.5
             สร้าง Trade (is_paper=True, open_price=current, tp=TP, sl=SL)
             อัปเดต paper_trader_rules.total_trades += 1
```

**Guard:** 1 rule = 1 open paper trade เสมอ ป้องกัน stacking

### Exit Manager

```
1. query open paper trades: is_paper=True AND close_price IS NULL
2. สำหรับแต่ละ open paper trade:
     current_price = latest tick price
     
     ถ้า (buy AND current >= tp) OR (sell AND current <= tp):
         close trade, profit = (tp - open) × volume
         rule.win_count += 1
     
     ถ้า (buy AND current <= sl) OR (sell AND current >= sl):
         close trade, profit = (sl - open) × volume  [negative]
     
     ถ้า momentum flip (compute 1 indicator):
         close trade at current_price
```

### TP Computation — Nearest S/R Level

```python
def compute_tp(current_price: float, direction: str, bars: pd.DataFrame) -> float:
    # ใช้ standard pivot points (มีใน indicator engine แล้ว)
    pp, r1, r2, s1, s2 = compute_pivot_std(prev_day_ohlc)
    
    if direction == "buy":
        candidates = [x for x in [r1, r2] if x > current_price]
        return min(candidates) if candidates else current_price + atr * 2
    else:
        candidates = [x for x in [s1, s2] if x < current_price]
        return max(candidates) if candidates else current_price - atr * 2
```

### Performance Targets

| Operation | Target |
|-----------|--------|
| Cache load (hit) | < 1ms |
| Bar fetch (per TF) | < 100ms |
| Indicator compute (per rule) | < 500ms |
| Total per tick | < 2s |

### Files to Create/Modify

```
api/services/paper_trader.py                      New — signal monitor + exit manager + cache
api/routers/market_tick.py                        Modify — add asyncio.create_task(_run_paper_trader())
api/routers/patterns.py                           Modify — เพิ่ม endpoint สำหรับ paper trade history
tests/test_paper_trader.py                        New
```

ไม่ต้องการ service ใหม่, Redis, หรือ Celery — ทำงานใน FastAPI process เดิม

### API Endpoints (เพิ่มเติม)

```
GET /api/paper-trades
  → list ของ paper trades ทั้งหมด (open + closed) แยกต่าม rule
  → fields: id, rule_id, direction, open_price, close_price, tp, sl, profit, status
```

### Acceptance Criteria

- [ ] `_run_paper_trader()` ถูก trigger ใน background task ทุกครั้งที่มี market-tick
- [ ] `load_active_rules()` ใช้ in-memory cache, query DB เฉพาะเมื่อ TTL expired (1hr)
- [ ] Signal Monitor compute เฉพาะ indicators ที่อยู่ใน active rules เท่านั้น
- [ ] Entry guard: ไม่สร้าง paper trade ถ้า rule นั้นมี open trade อยู่แล้ว
- [ ] TP คำนวณจาก nearest pivot S/R level ในทิศที่ถูกต้อง
- [ ] SL = ATR(14) × 1.5 จาก entry price
- [ ] Exit Manager ปิด trade เมื่อ price hit TP หรือ SL (ลำดับ 1-2 ก่อน momentum)
- [ ] Early exit เมื่อ momentum indicator พลิก (momentum slug แรกใน rule)
- [ ] `GET /api/paper-trades` คืน paper trade history ถูกต้อง
- [ ] paper_trader_rules.win_count อัปเดตเมื่อ trade ปิดด้วย win
- [ ] tick processing รวมทั้งหมด < 2 วินาที (วัดจาก test ที่ mock bars)
- [ ] pytest ผ่านทุก test รวม regression

---

## Implementation Order

```
Phase 3 → Phase 4 (ต้องทำตามลำดับ)

Phase 3 ก่อน:
  1. Migration 010 (patterns + paper_trader_rules tables)
  2. Pattern model + schema
  3. Pattern discovery algorithm + tests
  4. APScheduler cron integration
  5. API endpoints

Phase 4 หลัง:
  1. Paper trader service (cache + signal monitor + exit manager)
  2. Hook เข้า market_tick handler
  3. TP/SL computation
  4. API endpoint
  5. Integration tests

Phase 3 block Phase 4 — ต้องมี paper_trader_rules table และ active rules
ก่อนจึงจะ run signal monitor ได้
```

## Dependencies

- **Phase 2 must be live** ก่อน Phase 3 จะมี trade_indicator_signals ให้วิเคราะห์
- **Direction bug ใน EA ต้อง fix** (done) + **EA ต้อง restart** เพื่อ correct historical directions
- **APScheduler** เพิ่มใน `api/requirements.txt`
- **Indicator Engine** (REGISTRY + indicators) ต้อง accessible จาก paper_trader.py สำหรับ live compute

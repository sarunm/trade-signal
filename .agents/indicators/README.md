# Indicator Engine — Task Index

**Goal:** คำนวณ indicator ทุกตัวจาก price_bars ณ เวลา entry ของแต่ละ trade แล้วบันทึกว่า signal match กับ direction ของ trade หรือไม่ เพื่อให้ผู้ใช้เห็นว่าตัวเองเทรดตรงกับระบบไหน

**Block 0 — Infrastructure** ต้องทำก่อน — อยู่ใน `backlog.md` (task: Indicator Engine Infrastructure)

## กฎการหยิบงาน (Pickup Rule)

**Task ที่ไม่มี assignee** (ระบุว่า "ว่าง — ใครหยิบได้") → agent ใดก็หยิบได้ทันที โดย:
- หยิบ **ทีละ task เดียว** หรือ **เป็นชุดที่เกี่ยวข้องกัน** (เช่น indicators ทั้งกลุ่ม volume)
- อัปเดต assignee และ status ใน task ก่อน start ทันที
- ห้าม parallel: ถ้า agent A กำลังทำ volume group อยู่ agent B ต้องเลือก group อื่น
- Priority rule ยังใช้: normal ก่อน low เสมอ

## Task Files

| File | Group | # Tasks | Priority |
|------|-------|---------|----------|
| [trend.md](trend.md) | Trend | 29 | normal |
| [momentum.md](momentum.md) | Momentum / Oscillator | 39 | normal |
| [volume.md](volume.md) | Volume | 19 | low |
| [volatility.md](volatility.md) | Volatility | 15 | low |
| [sr.md](sr.md) | Support / Resistance | 18 | low |
| [pattern.md](pattern.md) | Pattern-Based | 9 | low |
| [cycle.md](cycle.md) | Cycle / Statistical | 13 | low |
| **Total** | | **142** | |

## Architecture (สรุป)

```
trade ปิด (order_state → filled/closed)
    │
    └── trade_logger.py: on_trade_close()
            │
            └── indicator_engine.compute_all(trade, bars)
                    │ async background task
                    ├── เรียก compute_X(bars) สำหรับทุก indicator ใน REGISTRY
                    ├── เทียบ direction กับ trade.direction
                    └── บันทึก trade_indicator_signals (DB)
```

## Task Format

```
#### IND-{GROUP}-{NN} | {Full Name} | `{slug}`

| Field | Value |
|-------|-------|
| priority | normal / low |
| pandas-ta | `df.ta.xxx()` หรือ custom |
| formula | สูตรย่อ |
| ref | URL |

**Match BUY:** เงื่อนไข
**Match SELL:** เงื่อนไข
**File:** `api/services/indicators/{group}/{slug}.py`
**AC:** acceptance criteria ย่อ
```

## REGISTRY Pattern (สำหรับ agent อ่าน)

```python
# api/services/indicator_engine.py
REGISTRY: dict[str, IndicatorFn] = {}

def register(slug: str):
    def decorator(fn):
        REGISTRY[slug] = fn
        return fn
    return decorator

# ใน api/services/indicators/trend/sma.py
@register("sma")
def compute_sma(bars: pd.DataFrame, direction: str) -> IndicatorResult:
    ...
```

## IndicatorResult Schema

```python
@dataclass
class IndicatorResult:
    slug: str
    value: float | None       # ค่า indicator หลัก ณ entry bar
    direction: str | None     # "bullish" | "bearish" | "neutral"
    matched: bool             # True ถ้า direction ตรงกับ trade
    timeframe: str            # เช่น "H1"
    metadata: dict            # ค่าเสริม เช่น {"signal": 0.3, "hist": -0.1}
```

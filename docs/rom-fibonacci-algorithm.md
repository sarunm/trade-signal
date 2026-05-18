# ROM (Rain On Me V2) — Fibonacci Algorithm Reference

Source: https://www.tradingview.com/script/Ix450pxu/ by RickSimpson  
Original pivot code credited to QuantNomad (Ultimate Pivot Points Alerts)

---

## Algorithm: Fibonacci Pivot Points

ROM ไม่ใช่ Fibonacci retracement จาก swing high/low แต่เป็น **Fibonacci Pivot Point** จาก previous period's OHLC

### Input

| Input | Default | Options |
|-------|---------|---------|
| `pp_period` | Day | Day, Week, Month, Year |

### Calculation

```
phigh  = previous period's highest high
plow   = previous period's lowest low
pclose = previous period's close

PP     = (phigh + plow + pclose) / 3          ← Pivot Point
range  = phigh - plow

R1     = PP + range × 0.235
R2     = PP + range × 0.382
R3     = PP + range × 0.500
R4     = PP + range × 0.618
R5     = PP + range × 0.728
R6     = PP + range × 1.000
R7     = PP + range × 1.235
R8     = PP + range × 1.328
R9     = PP + range × 1.500
R10    = PP + range × 1.618

S1     = PP - range × 0.235   (mirrors R1)
...
S10    = PP - range × 1.618   (mirrors R10)
```

### Key Ratios (non-standard)

ROM uses **0.235** (not 0.236) and **0.728** (not 0.786) — intentional, not a rounding error.

---

## How Our EA Implements It

File: `ea/TradeSignalBridge.mq5` → `ComputeFibLevels()`

```mql5
CopyHigh(symbol, PERIOD_D1, 1, 1, ph)   // index 1 = yesterday
CopyLow(symbol,  PERIOD_D1, 1, 1, pl)
CopyClose(symbol, PERIOD_D1, 1, 1, pc)

PP        = (ph + pl + pc) / 3
range     = ph - pl
direction = pclose > (ph + pl) / 2 ? "bullish" : "bearish"
```

Calls `OnInit()` immediately (no 60s wait), then every `OnTimer()` (60s).

---

## API Payload Structure

`POST /api/fib-levels`

```json
{
  "symbol": "GOLD",
  "timeframe": "D1",
  "swing_high": "<phigh>",
  "swing_low":  "<plow>",
  "direction":  "bullish|bearish",
  "levels": {
    "0.000": "<PP>",
    "0.235": "<R1>", "0.382": "<R2>", "0.5": "<R3>",
    "0.618": "<R4>", "0.728": "<R5>", "1.000": "<R6>",
    "1.235": "<R7>", "1.328": "<R8>", "1.500": "<R9>", "1.618": "<R10>"
  },
  "extensions": {
    "0.235": "<S1>", "0.382": "<S2>", "0.5": "<S3>",
    "0.618": "<S4>", "0.728": "<S5>", "1.000": "<S6>",
    "1.235": "<S7>", "1.328": "<S8>", "1.500": "<S9>", "1.618": "<S10>"
  },
  "computed_at": "<ISO8601>"
}
```

`swing_high` / `swing_low` = previous day's high/low (stored for display reference, not used for level calculation)

`levels["0.000"]` = PP (the central pivot)

---

## MT5 Chart Lines

| Object Name | Price | Color | Style |
|-------------|-------|-------|-------|
| `TSB_FIB_PP` | PP | Silver | Dashed |
| `TSB_FIB_R_0.235` … `TSB_FIB_R_1.618` | R1..R10 | MediumSeaGreen | Solid |
| `TSB_FIB_S_0.235` … `TSB_FIB_S_1.618` | S1..S10 | Tomato | Solid |

Cleanup prefix: `TSB_FIB_` — removed on `OnDeinit()` and before each redraw.

---

## What ROM Is NOT

- ❌ Not a swing high/low detector (ZigZag, fractal, etc.)
- ❌ Not a standard Fibonacci retracement (0.236 / 0.786 ratios)
- ✅ Standard daily pivot point formula with custom Fibonacci extension ratios

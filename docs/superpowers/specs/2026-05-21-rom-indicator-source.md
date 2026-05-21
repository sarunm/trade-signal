# Rain On Me V2 (ROM) — TradingView Indicator Source

**Author:** © RickSimpson  
**License:** Mozilla Public License 2.0 — https://mozilla.org/MPL/2.0/  
**Version:** Pine Script v4

---

## Fibonacci Method (Key Section)

ROM ใช้ **Classic Fibonacci Pivot Point**:

```
PP  = (prev_high + prev_low + prev_close) / 3
R/S = PP ± (prev_high - prev_low) * ratio
```

**Period input:** Day (default) | Week | Month | Year

**Ratios (10 levels ทั้ง R และ S):**

| Level | Ratio |
|-------|-------|
| 1 | 0.235 |
| 2 | 0.382 |
| 3 | 0.500 |
| 4 | 0.618 |
| 5 | 0.728 |
| 6 | 1.000 |
| 7 | 1.235 |
| 8 | 1.328 |
| 9 | 1.500 |
| 10 | 1.618 |

**Labels:** `PP`, `R1`–`R10` (green), `S1`–`S10` (red)

---

## Full Source Code

```pinescript
// This source code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/
// © RickSimpson
//@version=4

study(title="Rain On Me V2", shorttitle='ROM V2', overlay=true, max_bars_back=300)

//Inputs

showbs     = input(defval=true,  title="Show ATR?")
showvptbs  = input(defval=false, title="Show VPT?")
showsar    = input(defval=false, title="Show PSAR?")
showstrd   = input(defval=false, title="Show SuperTrend?")
showsr     = input(defval=true,  title="Show Support/Resistance Lines?")
showdivs   = input(defval=true,  title="Show Divergences?")
showbb     = input(defval=false, title="Show Bollinger?")
showichi   = input(defval=true,  title="Show Ichimoku?")
showtrline = input(defval=true,  title="Show Trendline?")
showfib    = input(defval=true,  title="Show Fibonacci?")
showpan    = input(defval=false, title="Show Fibonacci Info Panel?")

//ATR

atrper  = input(defval=14, title="ATR Period")
atrmult = input(defval=2,  title="ATR Multiplier", type=input.float, minval=0.5, maxval=100, step=0.1)

emasrc     = hlc3
emalen     = 200
useemacond = false
emaline    = ema(emasrc, emalen)
ratr       = atr(atrper)
nl         = atrmult * ratr

ratrts   = float(na)
ratrts  := iff(close > nz(ratrts[1], 0) and close[1] > nz(ratrts[1], 0), max(nz(ratrts[1]), close - nl), iff(close < nz(ratrts[1], 0) and close[1] < nz(ratrts[1], 0), min(nz(ratrts[1]), close + nl), iff(close > nz(ratrts[1], 0), close - nl, close + nl)))
indir    = int(na)
indir   := iff(close[1] < nz(ratrts[1], 0) and close > nz(ratrts[1], 0), 1, iff(close[1] > nz(ratrts[1], 0) and close < nz(ratrts[1], 0) and (useemacond ? close < emaline : true), -1, nz(indir[1], 0)))
posbear  = false
posbear := nz(posbear[1], false)
posbull  = false
posbull := nz(posbull[1], false)
atrsell  = not posbear and indir == -1
atrbuy   = not posbull and indir ==  1

if atrsell
    posbull := false
    posbear := true

if atrbuy
    posbull := true
    posbear := false

plotshape(showbs ? atrsell : na, title="ATR Sell", style=shape.labeldown, location=location.abovebar, size=size.tiny, text="atr",  textcolor=color.white, color=color.red,   transp=0)
plotshape(showbs ? atrbuy  : na, title="ATR Buy",  style=shape.labelup,   location=location.belowbar, size=size.tiny, text="atr",  textcolor=color.white, color=color.green, transp=0)

alertcondition(atrsell, title="Sell",  message='Sell')
alertcondition(atrbuy,  title="Buy",   message='Buy')

//Fibonacci

pp_period = input(defval="Day", title="Fibonacci Period", type=input.string, options=['Day','Week','Month','Year'])

pp_type                = "Fibonacci"
show_historical_levels = false
show_level_value       = true

is_newbar(res) =>
    ch = 0
    if(res == 'Y')
        t  = year(time('D'))
        ch := change(t) != 0 ? 1 : 0
    else
        t = time(res)
        ch := change(t) != 0 ? 1 : 0
    ch

nround(x) =>
    n = round(x / syminfo.mintick) * syminfo.mintick

RoundToTick( _price) => round(_price / syminfo.mintick) * syminfo.mintick

pp_res = pp_period == 'Day' ? 'D' : pp_period == 'Week' ? 'W' : pp_period == 'Month' ? 'M' : 'Y'

open_cur  = 0.0
open_cur := is_newbar(pp_res) ? open : open_cur[1]
popen     = 0.0
popen    := is_newbar(pp_res) ? open_cur[1] : popen[1]
high_cur  = 0.0
high_cur := is_newbar(pp_res) ? high : max(high_cur[1], high)
phigh     = 0.0
phigh    := is_newbar(pp_res) ? high_cur[1] : phigh[1]
low_cur   = 0.0
low_cur  := is_newbar(pp_res) ? low : min(low_cur[1], low)
plow      = 0.0
plow     := is_newbar(pp_res) ? low_cur[1] : plow[1]
pclose    = 0.0
pclose   := is_newbar(pp_res) ? close[1] : pclose[1]

PP = 0.0
R1 = 0.0, R2 = 0.0, R3 = 0.0, R4 = 0.0, R5 = 0.0, R6 = 0.0, R7 = 0.0, R8 = 0.0, R9 = 0.0, R10 = 0.0
S1 = 0.0, S2 = 0.0, S3 = 0.0, S4 = 0.0, S5 = 0.0, S6 = 0.0, S7 = 0.0, S8 = 0.0, S9 = 0.0, S10 = 0.0

if (pp_type == "Fibonacci")
    PP  := (phigh + plow + pclose) / 3
    R1  := PP + (phigh - plow) * 0.235
    S1  := PP - (phigh - plow) * 0.235
    R2  := PP + (phigh - plow) * 0.382
    S2  := PP - (phigh - plow) * 0.382
    R3  := PP + (phigh - plow) * 0.5
    S3  := PP - (phigh - plow) * 0.5
    R4  := PP + (phigh - plow) * 0.618
    S4  := PP - (phigh - plow) * 0.618
    R5  := PP + (phigh - plow) * 0.728
    S5  := PP - (phigh - plow) * 0.728
    R6  := PP + (phigh - plow) * 1.000
    S6  := PP - (phigh - plow) * 1.000
    R7  := PP + (phigh - plow) * 1.235
    S7  := PP - (phigh - plow) * 1.235
    R8  := PP + (phigh - plow) * 1.328
    S8  := PP - (phigh - plow) * 1.328
    R9  := PP + (phigh - plow) * 1.5
    S9  := PP - (phigh - plow) * 1.5
    R10 := PP + (phigh - plow) * 1.618
    S10 := PP - (phigh - plow) * 1.618
```

---

## Implementation Notes (สำหรับ MT5 EA)

- `phigh`, `plow`, `pclose` = previous **completed** period's H/L/C (ไม่ใช่ current period)
- Default period = Day → ใช้ previous day's H/L/C
- Levels reset ทุกต้นงวดใหม่ (new Day/Week/Month/Year bar)
- **ผู้ใช้ยืนยัน: period = Week** → ใช้ previous week's H/L/C เสมอ

# Pattern-Based Indicators — 9 Tasks

**assignee:** (ว่าง — ใครหยิบได้) | **priority:** low | **group:** pattern

ทุก task block กับ **Indicator Engine Infrastructure**

---

#### IND-P-01 | Fractals (Bill Williams) | `fractals`

| Field | Value |
|-------|-------|
| pandas-ta | custom: 5-bar pattern |
| formula | Bullish Fractal: bar[2].Low < bar[0,1,3,4].Low; Bearish Fractal: bar[2].High > bar[0,1,3,4].High |
| ref | https://www.investopedia.com/terms/f/fractal.asp |

**Match BUY:** bullish fractal ที่ bar entry (swing low confirmation)  
**Match SELL:** bearish fractal ที่ bar entry  
**File:** `api/services/indicators/pattern/fractals.py`  
**AC:** `compute_fractals(bars)` คืน bull/bear fractal flags, registered, pytest ผ่าน

---

#### IND-P-02 | Heikin-Ashi | `heikinashi`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.ha()` → `HA_open`, `HA_high`, `HA_low`, `HA_close` |
| formula | HA_C=(O+H+L+C)/4; HA_O=(HA_O_prev+HA_C_prev)/2; HA_H=max(H,HA_O,HA_C); HA_L=min(L,HA_O,HA_C) |
| ref | https://school.stockcharts.com/doku.php?id=chart_analysis:heikin_ashi |

**Match BUY:** HA bar เป็น bullish (HA_C > HA_O) และไม่มี lower shadow (HA_L = HA_O)  
**Match SELL:** HA bar เป็น bearish และไม่มี upper shadow  
**File:** `api/services/indicators/pattern/heikinashi.py`  
**AC:** `compute_heikinashi(bars)`, HA OHLC ถูกต้อง, no-shadow detection, registered, pytest ผ่าน

---

#### IND-P-03 | Candlestick Patterns | `candle_pattern`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.cdl_pattern(name="all")` หรือ specific patterns |
| formula | ตรวจ pattern ยอดนิยม: Doji, Hammer, Hanging Man, Engulfing, Morning Star, Evening Star, Harami |
| ref | https://school.stockcharts.com/doku.php?id=chart_analysis:candlestick_pattern_dictionary |

**Match BUY:** bullish pattern detected ที่ entry bar (Hammer, Bullish Engulfing, Morning Star)  
**Match SELL:** bearish pattern detected (Shooting Star, Bearish Engulfing, Evening Star)  
**File:** `api/services/indicators/pattern/candle_pattern.py`  
**AC:** `compute_candle_pattern(bars)` detect ≥5 patterns, direction=bullish/bearish, registered, pytest ผ่าน

---

#### IND-P-04 | Market Facilitation Index (BW MFI) | `bw_mfi`

| Field | Value |
|-------|-------|
| pandas-ta | custom |
| formula | MFI = (High − Low) / tick_volume |
| ref | https://www.investopedia.com/terms/m/market-facilitation-index.asp |

**Match BUY:** MFI สูงกว่า prev bar AND Vol สูงกว่า prev bar (Green = ease of upward movement)  
**Match SELL:** MFI สูงกว่า prev bar AND Vol สูงกว่า prev bar พร้อม close < open  
**File:** `api/services/indicators/pattern/bw_mfi.py`  
**AC:** `compute_bw_mfi(bars)`, 4 color categories ถูกต้อง (Green/Fade/Fake/Squat), registered, pytest ผ่าน

---

#### IND-P-05 | Renko | `renko`

| Field | Value |
|-------|-------|
| pandas-ta | custom: brick size = ATR(14) |
| formula | New brick เมื่อ price เคลื่อน ≥ brick_size; ไม่สนใจเวลา |
| ref | https://school.stockcharts.com/doku.php?id=chart_analysis:renko_charts |

**Match BUY:** Renko brick ณ เวลา entry เป็น green (up brick)  
**Match SELL:** brick เป็น red (down brick)  
**File:** `api/services/indicators/pattern/renko.py`  
**AC:** `compute_renko(bars, brick_size_atr=14)`, brick sequence ถูกต้อง, registered, pytest ผ่าน

---

#### IND-P-06 | Point & Figure | `pnf`

| Field | Value |
|-------|-------|
| pandas-ta | custom: box_size = ATR(14); reversal = 3 boxes |
| formula | X column เพิ่มเมื่อ price ขึ้น ≥ box_size; O column เพิ่มเมื่อ price ลง ≥ reversal×box_size |
| ref | https://school.stockcharts.com/doku.php?id=chart_analysis:point_and_figure |

**Match BUY:** P&F column เป็น X (demand > supply) ณ เวลา entry  
**Match SELL:** column เป็น O  
**File:** `api/services/indicators/pattern/pnf.py`  
**AC:** `compute_pnf(bars)`, column type detection ถูกต้อง, registered, pytest ผ่าน

---

#### IND-P-07 | Kagi Charts | `kagi`

| Field | Value |
|-------|-------|
| pandas-ta | custom |
| formula | เส้นต่อเมื่อ price reverse ≥ reversal% (default 1%); Yang = bullish line (thick); Yin = bearish (thin) |
| ref | https://school.stockcharts.com/doku.php?id=chart_analysis:kagi_charts |

**Match BUY:** Kagi line เป็น Yang (thick/bullish) ณ เวลา entry  
**Match SELL:** line เป็น Yin  
**File:** `api/services/indicators/pattern/kagi.py`  
**AC:** `compute_kagi(bars, reversal=0.01)`, Yang/Yin classification ถูกต้อง, registered, pytest ผ่าน

---

#### IND-P-08 | Three-Line Break | `tlb`

| Field | Value |
|-------|-------|
| pandas-ta | custom |
| formula | New line เฉพาะเมื่อ close เกิน/ต่ำกว่า high/low ของ 3 lines ก่อนหน้า |
| ref | https://school.stockcharts.com/doku.php?id=chart_analysis:three_line_break |

**Match BUY:** TLB line สีขาว/เขียว (bullish reversal)  
**Match SELL:** TLB line สีดำ/แดง  
**File:** `api/services/indicators/pattern/tlb.py`  
**AC:** `compute_tlb(bars)`, 3-line lookback logic ถูกต้อง, registered, pytest ผ่าน

---

#### IND-P-09 | Range Expansion Index (Pattern Use) | `rei_pattern`

| Field | Value |
|-------|-------|
| pandas-ta | ใช้ `compute_rei` จาก IND-S-16; เพิ่ม pattern context |
| formula | ตรวจ bar conditions: 2-bar high/low ที่ใช้ใน REI numerator |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:range_expansion_index_rei |

**Match BUY:** REI เพิ่งออกจาก oversold zone (crossing −60 upward)  
**Match SELL:** REI เพิ่งออกจาก overbought zone (crossing +60 downward)  
**File:** `api/services/indicators/pattern/rei_pattern.py`  
**AC:** `compute_rei_pattern(bars)`, crossover detection ถูกต้อง, registered, pytest ผ่าน

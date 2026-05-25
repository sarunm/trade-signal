# Support / Resistance & Price Level Indicators — 18 Tasks

**assignee:** claude | **status:** done | **priority:** low | **group:** sr

ทุก task block กับ **Indicator Engine Infrastructure**

---

#### IND-S-01 | Pivot Points (Standard) | `pivot_std`

| Field | Value |
|-------|-------|
| pandas-ta | custom: คำนวณจาก D timeframe OHLC ของวันก่อน |
| formula | PP=(H+L+C)/3; R1=2PP−L; S1=2PP−H; R2=PP+(H−L); S2=PP−(H−L) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:pivot_points |

**Match BUY:** entry price ≤ S1 (เทรดจากแนวรับ)  
**Match SELL:** entry price ≥ R1  
**File:** `api/services/indicators/sr/pivot_std.py`  
**AC:** `compute_pivot_std(prev_day_ohlc)` คืน PP/R1/R2/R3/S1/S2/S3, registered, pytest ผ่าน

---

#### IND-S-02 | Woodie Pivot Points | `pivot_woodie`

| Field | Value |
|-------|-------|
| pandas-ta | custom |
| formula | PP=(H+L+2C)/4; R1=2PP−L; S1=2PP−H; R2=PP+(H−L); S2=PP−(H−L) |
| ref | https://www.investopedia.com/terms/w/woodiespivotpoint.asp |

**Match BUY:** entry price ≤ S1  
**Match SELL:** entry price ≥ R1  
**File:** `api/services/indicators/sr/pivot_woodie.py`  
**AC:** `compute_pivot_woodie(prev_day_ohlc)`, formula ต่างจาก standard ถูกต้อง, registered, pytest ผ่าน

---

#### IND-S-03 | Camarilla Pivot Points | `pivot_camarilla`

| Field | Value |
|-------|-------|
| pandas-ta | custom |
| formula | H4=C+(H−L)×1.1/2; H3=C+(H−L)×1.1/4; L3=C−(H−L)×1.1/4; L4=C−(H−L)×1.1/2 |
| ref | https://www.investopedia.com/terms/c/camarilla.asp |

**Match BUY:** entry price ≤ L3 (potential reversal up from Camarilla support)  
**Match SELL:** entry price ≥ H3  
**File:** `api/services/indicators/sr/pivot_camarilla.py`  
**AC:** `compute_pivot_camarilla(prev_day_ohlc)`, H3/H4/L3/L4 ถูกต้อง, registered, pytest ผ่าน

---

#### IND-S-04 | Fibonacci Pivot Points | `pivot_fib`

| Field | Value |
|-------|-------|
| pandas-ta | custom |
| formula | PP=(H+L+C)/3; R1=PP+0.382×(H−L); R2=PP+0.618×(H−L); R3=PP+(H−L); S1=PP−0.382×(H−L); S2=PP−0.618×(H−L) |
| ref | https://www.investopedia.com/terms/f/fibonaccipivotpoints.asp |

**Match BUY:** entry price ≤ S1  
**Match SELL:** entry price ≥ R1  
**File:** `api/services/indicators/sr/pivot_fib.py`  
**AC:** `compute_pivot_fib(prev_day_ohlc)`, Fib ratios ถูกต้อง, registered, pytest ผ่าน

---

#### IND-S-05 | DeMark Pivot Points | `pivot_demark`

| Field | Value |
|-------|-------|
| pandas-ta | custom |
| formula | X=H+2L+C ถ้า Close<Open; X=2H+L+C ถ้า Close>Open; X=H+L+2C ถ้า Close=Open; PP=X/4; R1=X/2−L; S1=X/2−H |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:demark_pivots |

**Match BUY:** entry ≤ S1  
**Match SELL:** entry ≥ R1  
**File:** `api/services/indicators/sr/pivot_demark.py`  
**AC:** `compute_pivot_demark(prev_day_ohlc)`, open/close condition ถูกต้อง, registered, pytest ผ่าน

---

#### IND-S-06 | Fibonacci Retracement | `fib_retracement`

| Field | Value |
|-------|-------|
| pandas-ta | custom: หา swing high/low ใน N bars แล้วคำนวณ Fib levels |
| formula | Levels = swing_high − (swing_high−swing_low) × ratio; ratios=[0.236,0.382,0.5,0.618,0.786] |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:fibonacci_retracements |

**Match BUY:** entry price อยู่ใกล้ (±ATR/2) Fib support level (0.382, 0.5, 0.618)  
**Match SELL:** entry price อยู่ใกล้ Fib resistance level  
**File:** `api/services/indicators/sr/fib_retracement.py`  
**AC:** `compute_fib_retracement(bars, swing_n=50)`, nearest level detection ถูกต้อง, registered, pytest ผ่าน

---

#### IND-S-07 | Fibonacci Extensions | `fib_extension`

| Field | Value |
|-------|-------|
| pandas-ta | custom: หา 3 swing points แล้ว project target |
| formula | Ext_levels = swing_C + (swing_A−swing_B) × ratio; ratios=[1.272,1.618,2.0,2.618] |
| ref | https://www.investopedia.com/terms/f/fibonacciextensions.asp |

**Match BUY:** trade TP อยู่ใกล้ Fib extension level  
**Match SELL:** trade TP อยู่ใกล้ Fib extension level  
**File:** `api/services/indicators/sr/fib_extension.py`  
**AC:** `compute_fib_extension(swing_a, swing_b, swing_c)`, projection ถูกต้อง, registered, pytest ผ่าน

---

#### IND-S-08 | Fibonacci Fan | `fib_fan`

| Field | Value |
|-------|-------|
| pandas-ta | custom: trendlines จาก swing low ที่มุม Fib |
| formula | Fan lines from swing_low crossing swing_high at t=T: slope × ratio for ratio=[0.382,0.5,0.618] |
| ref | https://www.investopedia.com/terms/f/fibonaccifan.asp |

**Match BUY:** close อยู่เหนือ Fan line 0.618 (support zone)  
**Match SELL:** close อยู่ต่ำกว่า Fan line 0.382  
**File:** `api/services/indicators/sr/fib_fan.py`  
**AC:** `compute_fib_fan(bars, swing_idx)`, fan level interpolation ถูกต้อง, registered, pytest ผ่าน

---

#### IND-S-09 | Fibonacci Time Zones | `fib_time`

| Field | Value |
|-------|-------|
| pandas-ta | custom: แนวตั้งที่ระยะ Fib จาก swing |
| formula | Time zone bars = base_period × [1,1,2,3,5,8,13,21,34,55,89,...] |
| ref | https://www.investopedia.com/terms/f/fibonaccicluster.asp |

**Match BUY หรือ SELL:** entry bar อยู่ใน ±2 bars ของ Fib time zone (potential turning point)  
**File:** `api/services/indicators/sr/fib_time.py`  
**AC:** `compute_fib_time(bars, anchor_idx)`, Fibonacci sequence ถูกต้อง, registered, pytest ผ่าน

---

#### IND-S-10 | Murrey Math Lines | `murrey`

| Field | Value |
|-------|-------|
| pandas-ta | custom |
| formula | แบ่ง price range เป็น 8 ส่วนเท่ากัน (octaves) จาก round numbers; key levels = 0/8, 4/8 (PP), 8/8 |
| ref | https://www.investopedia.com/terms/m/murrey-math-lines.asp |

**Match BUY:** entry อยู่ใกล้ 2/8 หรือ 3/8 line (strong support)  
**Match SELL:** entry อยู่ใกล้ 5/8 หรือ 6/8 line (strong resistance)  
**File:** `api/services/indicators/sr/murrey.py`  
**AC:** `compute_murrey(bars, period=64)`, 8 octave levels ถูกต้อง, registered, pytest ผ่าน

---

#### IND-S-11 | Gann HiLo Activator | `gann_hilo`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.gannhilo(high_length=13, low_length=21)` → `GHLl_13_21`, `GHLs_13_21` |
| formula | ถ้า Close > SMA(High,13): ใช้ SMA(Low,21) เป็น support line; ถ้า Close < SMA(Low,21): ใช้ SMA(High,13) |
| ref | https://library.tradingtechnologies.com/trade/chrt-ti-gann-hilo-activator.html |

**Match BUY:** GHLl ไม่เป็น NaN (bullish mode)  
**Match SELL:** GHLs ไม่เป็น NaN (bearish mode)  
**File:** `api/services/indicators/sr/gann_hilo.py`  
**AC:** `compute_gann_hilo(bars)`, mode detection ถูกต้อง, registered, pytest ผ่าน

---

#### IND-S-12 | Price Channels | `price_channel`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.donchian(lower_length=20, upper_length=20)` — ใช้ร่วมกับ IND-X-05 |
| formula | Upper=max(High,20); Lower=min(Low,20); Mid=(Upper+Lower)/2 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:price_channels |

**Match BUY:** close breaks above Upper (breakout)  
**Match SELL:** close breaks below Lower  
**File:** `api/services/indicators/sr/price_channel.py`  
**AC:** `compute_price_channel(bars, period=20)`, breakout detection, registered, pytest ผ่าน

---

#### IND-S-13 | ZigZag | `zigzag`

| Field | Value |
|-------|-------|
| pandas-ta | custom: filter swings < deviation% |
| formula | New swing ถ้า price เปลี่ยน ≥ deviation% จาก last swing point (default 5%) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:zigzag |

**Match BUY:** entry อยู่ใกล้ ZigZag swing low (±ATR)  
**Match SELL:** entry อยู่ใกล้ ZigZag swing high  
**File:** `api/services/indicators/sr/zigzag.py`  
**AC:** `compute_zigzag(bars, deviation=0.05)`, swing detection ถูกต้อง, registered, pytest ผ่าน

---

#### IND-S-14 | Volume by Price | `vbp`

| Field | Value |
|-------|-------|
| pandas-ta | custom: histogram ตาม price bucket |
| formula | แบ่ง price range N price bins; นับ tick_volume ใน bin; POC = bin ที่มี volume สูงสุด |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:volume_by_price |

**Match BUY:** entry อยู่ใต้ POC (potential support เนื่องจาก high-volume zone)  
**Match SELL:** entry อยู่เหนือ POC  
**File:** `api/services/indicators/sr/vbp.py`  
**AC:** `compute_vbp(bars, bins=20)`, POC identification ถูกต้อง, registered, pytest ผ่าน

---

#### IND-S-15 | Chandelier Exit | `chandelier`

| Field | Value |
|-------|-------|
| pandas-ta | custom: `df.ta.atr()` + highest high / lowest low |
| formula | Long exit = max(High,N) − ATR(22)×3; Short exit = min(Low,N) + ATR(22)×3 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:chandelier_exit |

**Match BUY:** close > Chandelier Long Exit level (still in long trend)  
**Match SELL:** close < Chandelier Short Exit level  
**File:** `api/services/indicators/sr/chandelier.py`  
**AC:** `compute_chandelier(bars, period=22, mult=3)`, trailing stop ถูกต้อง, registered, pytest ผ่าน

---

#### IND-S-16 | DeMark Range Expansion Index | `rei`

| Field | Value |
|-------|-------|
| pandas-ta | custom |
| formula | REI = Σ(num, 8) / Σ(denom, 8) × 100; num = 0 ถ้า bars ตรงกับ range contraction conditions |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:range_expansion_index_rei |

**Match BUY:** REI < −60 (oversold range exhaustion)  
**Match SELL:** REI > +60  
**File:** `api/services/indicators/sr/rei.py`  
**AC:** `compute_rei(bars)`, numerator/denominator logic ถูกต้อง, registered, pytest ผ่าน

---

#### IND-S-17 | Standard Error Bands | `se_bands`

| Field | Value |
|-------|-------|
| pandas-ta | custom: linreg ± 2×StdErr |
| formula | SE = StdDev(residuals) / sqrt(N); Bands = LinReg ± 2×SE |
| ref | https://library.tradingtechnologies.com/trade/chrt-ti-standard-error-bands.html |

**Match BUY:** close ≤ lower SE band  
**Match SELL:** close ≥ upper SE band  
**File:** `api/services/indicators/sr/se_bands.py`  
**AC:** `compute_se_bands(bars, period=21)`, StdErr formula ถูกต้อง, registered, pytest ผ่าน

---

#### IND-S-18 | DeMark Projected Range | `demark_proj`

| Field | Value |
|-------|-------|
| pandas-ta | custom |
| formula | ถ้า Close>Open: Proj_H=2C+H−L; Proj_L=2L+H−C; ถ้า Close<Open: Proj_H=2H+C−L; Proj_L=2C+L−H; ถ้า Close=Open: Proj_H=H+C−L; Proj_L=L+C−H; divide each by 2 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:demark_s_range_projections |

**Match BUY:** trade entry อยู่ใกล้ Projected Low  
**Match SELL:** trade entry อยู่ใกล้ Projected High  
**File:** `api/services/indicators/sr/demark_proj.py`  
**AC:** `compute_demark_proj(prev_ohlc)` คืน proj_high/proj_low, registered, pytest ผ่าน

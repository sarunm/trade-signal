# Trend Indicators — 29 Tasks

**assignee:** codex | **status:** done | **priority:** normal | **group:** trend

ทุก task ใน file นี้ block อยู่กับ **Indicator Engine Infrastructure** (ต้องทำก่อน)

---

#### IND-T-01 | Simple Moving Average | `sma`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.sma(length=20)` → `SMA_20` |
| formula | SMA(N) = (C₁+C₂+…+Cₙ) / N |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:moving_averages |

**Match BUY:** close > SMA_20 ที่ entry bar  
**Match SELL:** close < SMA_20 ที่ entry bar  
**File:** `api/services/indicators/trend/sma.py`  
**AC:** `compute_sma(bars, period=20)` คืน IndicatorResult, ลงทะเบียนใน REGISTRY["sma"], pytest ผ่าน

---

#### IND-T-02 | Exponential Moving Average | `ema`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.ema(length=20)` → `EMA_20` |
| formula | EMA = Close × k + EMA_prev × (1−k) where k = 2/(N+1) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:moving_averages |

**Match BUY:** close > EMA_20 ที่ entry bar  
**Match SELL:** close < EMA_20 ที่ entry bar  
**File:** `api/services/indicators/trend/ema.py`  
**AC:** `compute_ema(bars, period=20)` ผล EMA ถูกต้อง, registered, pytest ผ่าน

---

#### IND-T-03 | Double EMA | `dema`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.dema(length=20)` → `DEMA_20` |
| formula | DEMA = 2×EMA(N) − EMA(EMA(N)) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:dema |

**Match BUY:** close > DEMA_20  
**Match SELL:** close < DEMA_20  
**File:** `api/services/indicators/trend/dema.py`  
**AC:** `compute_dema(bars, period=20)`, registered, pytest ผ่าน

---

#### IND-T-04 | Triple EMA | `tema`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.tema(length=20)` → `TEMA_20` |
| formula | TEMA = 3×EMA₁ − 3×EMA₂ + EMA₃ |
| ref | https://www.investopedia.com/terms/t/triple-exponential-moving-average.asp |

**Match BUY:** close > TEMA_20  
**Match SELL:** close < TEMA_20  
**File:** `api/services/indicators/trend/tema.py`  
**AC:** `compute_tema(bars, period=20)`, registered, pytest ผ่าน

---

#### IND-T-05 | Weighted Moving Average | `wma`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.wma(length=20)` → `WMA_20` |
| formula | WMA(N) = Σ(weight_i × Close_i) / Σ(weight_i); weight_i = i |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:weighted_moving_average |

**Match BUY:** close > WMA_20  
**Match SELL:** close < WMA_20  
**File:** `api/services/indicators/trend/wma.py`  
**AC:** `compute_wma(bars, period=20)`, registered, pytest ผ่าน

---

#### IND-T-06 | Hull Moving Average | `hma`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.hma(length=20)` → `HMA_20` |
| formula | HMA = WMA(2×WMA(N/2) − WMA(N), √N) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:hull_moving_average |

**Match BUY:** close > HMA_20  
**Match SELL:** close < HMA_20  
**File:** `api/services/indicators/trend/hma.py`  
**AC:** `compute_hma(bars, period=20)`, registered, pytest ผ่าน

---

#### IND-T-07 | Kaufman's Adaptive Moving Average | `kama`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.kama(length=10, fast=2, slow=30)` → `KAMA_10_2_30` |
| formula | KAMA = KAMA_prev + SC² × (Close − KAMA_prev); SC = ER × (fast_sc−slow_sc) + slow_sc |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:kaufman_s_adaptive_moving_average |

**Match BUY:** close > KAMA  
**Match SELL:** close < KAMA  
**File:** `api/services/indicators/trend/kama.py`  
**AC:** `compute_kama(bars)`, registered, pytest ผ่าน

---

#### IND-T-08 | McGinley Dynamic | `mcgd`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.mcgd(length=14)` → `MCGD_14` |
| formula | MD = MD_prev + (Close − MD_prev) / (N × (Close/MD_prev)⁴) |
| ref | https://www.investopedia.com/articles/trading/10/mcginley-dynamic-indicator.asp |

**Match BUY:** close > MCGD  
**Match SELL:** close < MCGD  
**File:** `api/services/indicators/trend/mcgd.py`  
**AC:** `compute_mcgd(bars)`, registered, pytest ผ่าน

---

#### IND-T-09 | T3 Moving Average | `t3`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.t3(length=5, a=0.7)` → `T3_5_0.7` |
| formula | T3 = c₁×EMA6 + c₂×EMA5 + c₃×EMA4 + c₄×EMA3 + c₅×EMA2 + c₆×EMA1 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:t3_moving_average |

**Match BUY:** close > T3  
**Match SELL:** close < T3  
**File:** `api/services/indicators/trend/t3.py`  
**AC:** `compute_t3(bars)`, registered, pytest ผ่าน

---

#### IND-T-10 | Zero Lag EMA | `zlma`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.zlma(length=20)` → `ZLMA_20` |
| formula | ZLMA = EMA(2×Close − EMA(Close, lag), N) where lag = floor((N−1)/2) |
| ref | https://www.investopedia.com/articles/trading/10/zero-lag-indicator.asp |

**Match BUY:** close > ZLMA  
**Match SELL:** close < ZLMA  
**File:** `api/services/indicators/trend/zlma.py`  
**AC:** `compute_zlma(bars)`, registered, pytest ผ่าน

---

#### IND-T-11 | MACD | `macd`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.macd(fast=12, slow=26, signal=9)` → `MACD_12_26_9`, `MACDh_12_26_9`, `MACDs_12_26_9` |
| formula | MACD = EMA12 − EMA26; Signal = EMA9(MACD); Hist = MACD − Signal |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:macd-histogram |

**Match BUY:** MACD > Signal (histogram > 0) ที่ entry bar  
**Match SELL:** MACD < Signal (histogram < 0) ที่ entry bar  
**File:** `api/services/indicators/trend/macd.py`  
**AC:** `compute_macd(bars)` คืน value=histogram, direction="bullish" ถ้า hist>0, registered, pytest ผ่าน

---

#### IND-T-12 | Parabolic SAR | `psar`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.psar(af0=0.02, af=0.02, max_af=0.2)` → `PSARl_0.02_0.2`, `PSARs_0.02_0.2` |
| formula | SAR = SAR_prev + AF × (EP − SAR_prev); AF ปรับทุกครั้งที่เกิด extreme point |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:parabolic_sar |

**Match BUY:** PSARl ไม่เป็น NaN (SAR อยู่ใต้ราคา = uptrend)  
**Match SELL:** PSARs ไม่เป็น NaN (SAR อยู่เหนือราคา = downtrend)  
**File:** `api/services/indicators/trend/psar.py`  
**AC:** `compute_psar(bars)`, registered, pytest ผ่าน

---

#### IND-T-13 | Average Directional Index | `adx`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.adx(length=14)` → `ADX_14`, `DMP_14`, `DMN_14` |
| formula | ADX = EMA(|+DI − −DI| / (+DI + −DI), 14) × 100; +DI = EMA(+DM)/ATR |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:average_directional_index_adx |

**Match BUY:** ADX > 25 AND DMP > DMN  
**Match SELL:** ADX > 25 AND DMN > DMP  
**File:** `api/services/indicators/trend/adx.py`  
**AC:** `compute_adx(bars)`, direction จาก DMP vs DMN เมื่อ ADX>25, registered, pytest ผ่าน

---

#### IND-T-14 | Ichimoku Cloud | `ichimoku`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.ichimoku(tenkan=9, kijun=26, senkou=52)` → multiple columns |
| formula | Tenkan=(H9+L9)/2; Kijun=(H26+L26)/2; Senkou_A=(Tenkan+Kijun)/2 shifted+26; Senkou_B=(H52+L52)/2 shifted+26 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:ichimoku_cloud |

**Match BUY:** close > max(Senkou_A, Senkou_B) AND Tenkan ≥ Kijun  
**Match SELL:** close < min(Senkou_A, Senkou_B) AND Tenkan ≤ Kijun  
**File:** `api/services/indicators/trend/ichimoku.py`  
**AC:** `compute_ichimoku(bars)`, cloud position detection ถูกต้อง, registered, pytest ผ่าน

---

#### IND-T-15 | Aroon Indicator | `aroon`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.aroon(length=25)` → `AROOND_25`, `AROONU_25` |
| formula | Aroon Up = ((N − periods since N-period High) / N) × 100 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:aroon |

**Match BUY:** Aroon Up > 70 AND Aroon Down < 30  
**Match SELL:** Aroon Down > 70 AND Aroon Up < 30  
**File:** `api/services/indicators/trend/aroon.py`  
**AC:** `compute_aroon(bars)`, threshold logic ถูกต้อง, registered, pytest ผ่าน

---

#### IND-T-16 | Aroon Oscillator | `aroon_osc`

| Field | Value |
|-------|-------|
| pandas-ta | คำนวณจาก aroon: `AROONU − AROOND` |
| formula | Aroon Oscillator = Aroon Up − Aroon Down; range −100 ถึง +100 |
| ref | https://www.investopedia.com/terms/a/aroonoscillator.asp |

**Match BUY:** Aroon Oscillator > 0  
**Match SELL:** Aroon Oscillator < 0  
**File:** `api/services/indicators/trend/aroon_osc.py`  
**AC:** `compute_aroon_osc(bars)`, registered, pytest ผ่าน

---

#### IND-T-17 | Supertrend | `supertrend`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.supertrend(length=7, multiplier=3.0)` → `SUPERT_7_3.0`, `SUPERTd_7_3.0` |
| formula | Upper = (H+L)/2 + mult×ATR; Lower = (H+L)/2 − mult×ATR; พลิกเมื่อ close ทะลุ |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:supertrend |

**Match BUY:** SUPERTd = 1 (bullish mode)  
**Match SELL:** SUPERTd = -1 (bearish mode)  
**File:** `api/services/indicators/trend/supertrend.py`  
**AC:** `compute_supertrend(bars)`, direction จาก SUPERTd, registered, pytest ผ่าน

---

#### IND-T-18 | Alligator (Bill Williams) | `alligator`

| Field | Value |
|-------|-------|
| pandas-ta | custom — pandas-ta ไม่มี; ใช้ `df.ta.smma()` หรือ SMMA manual |
| formula | Jaw=SMMA(13,8-shift); Teeth=SMMA(8,5-shift); Lips=SMMA(5,3-shift) |
| ref | https://www.investopedia.com/terms/a/alligator-indicator.asp |

**Match BUY:** Lips > Teeth > Jaw (เส้นเรียงบน = bullish)  
**Match SELL:** Lips < Teeth < Jaw (เส้นเรียงล่าง = bearish)  
**File:** `api/services/indicators/trend/alligator.py`  
**AC:** `compute_alligator(bars)` คำนวณ Jaw/Teeth/Lips ถูกต้อง, registered, pytest ผ่าน

---

#### IND-T-19 | Vortex Indicator | `vortex`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.vortex(length=14)` → `VTXP_14`, `VTXM_14` |
| formula | VI+ = Σ|H−L_prev| / Σ(ATR, N); VI− = Σ|L−H_prev| / Σ(ATR, N) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:vortex_indicator |

**Match BUY:** VI+ > VI−  
**Match SELL:** VI− > VI+  
**File:** `api/services/indicators/trend/vortex.py`  
**AC:** `compute_vortex(bars)`, registered, pytest ผ่าน

---

#### IND-T-20 | Schaff Trend Cycle | `stc`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.stc(tclength=10, fast=23, slow=50, factor=0.5)` → `STC_10_23_50_0.5` |
| formula | STC = Stochastic(MACD, N) แบบ smoothed; range 0–100 |
| ref | https://www.investopedia.com/articles/trading/10/schaff-trend-cycle-indicator.asp |

**Match BUY:** STC > 25 หรือ crossing ขึ้น  
**Match SELL:** STC < 75 หรือ crossing ลง  
**File:** `api/services/indicators/trend/stc.py`  
**AC:** `compute_stc(bars)`, registered, pytest ผ่าน

---

#### IND-T-21 | MESA Adaptive Moving Average | `mama`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.mama(fastlimit=0.5, slowlimit=0.05)` → `MAMA_0.5_0.05`, `FAMA_0.5_0.05` |
| formula | MAMA ใช้ Hilbert Transform วัด phase angle เพื่อปรับ alpha; FAMA = EMA ช้าของ MAMA |
| ref | https://www.investopedia.com/terms/m/mesa-adaptive-moving-average.asp |

**Match BUY:** MAMA > FAMA  
**Match SELL:** MAMA < FAMA  
**File:** `api/services/indicators/trend/mama.py`  
**AC:** `compute_mama(bars)`, registered, pytest ผ่าน

---

#### IND-T-22 | Moving Average Envelopes | `ma_envelopes`

| Field | Value |
|-------|-------|
| pandas-ta | custom: SMA(20) ± 2.5% |
| formula | Upper = SMA(N) × (1 + pct); Lower = SMA(N) × (1 − pct) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:moving_average_envelopes |

**Match BUY:** close ≤ Lower band (ราคาต่ำกว่า envelope ล่าง)  
**Match SELL:** close ≥ Upper band (ราคาสูงกว่า envelope บน)  
**File:** `api/services/indicators/trend/ma_envelopes.py`  
**AC:** `compute_ma_envelopes(bars, period=20, pct=0.025)`, registered, pytest ผ่าน

---

#### IND-T-23 | Moving Average Ribbon | `ma_ribbon`

| Field | Value |
|-------|-------|
| pandas-ta | หลาย EMA: periods=[5,10,15,20,25,30,35,40,45,50] |
| formula | EMA ribbon = กลุ่ม EMA หลาย period; aligned = ทุกเส้นเรียงลำดับ |
| ref | https://www.investopedia.com/articles/trading/09/moving-average-ribbon.asp |

**Match BUY:** ทุก EMA เรียงลำดับจากมากไปน้อย (EMA5 > EMA10 > … > EMA50)  
**Match SELL:** ทุก EMA เรียงลำดับจากน้อยไปมาก (EMA5 < EMA10 < … < EMA50)  
**File:** `api/services/indicators/trend/ma_ribbon.py`  
**AC:** `compute_ma_ribbon(bars)`, ribbon alignment detection ถูกต้อง, registered, pytest ผ่าน

---

#### IND-T-24 | Linear Regression Line | `linreg`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.linreg(length=14)` → `LR_14` |
| formula | y = mx + b (OLS regression ผ่าน N bar สุดท้าย); slope > 0 = uptrend |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:linear_regression |

**Match BUY:** slope > 0 (เส้น regression ชี้ขึ้น)  
**Match SELL:** slope < 0 (เส้น regression ชี้ลง)  
**File:** `api/services/indicators/trend/linreg.py`  
**AC:** `compute_linreg(bars, period=14)` คืน slope, direction, registered, pytest ผ่าน

---

#### IND-T-25 | Vortex Indicator (already IND-T-19) — ข้ามไป

*(merged)*

---

#### IND-T-25 | Pring's Special K | `special_k`

| Field | Value |
|-------|-------|
| pandas-ta | custom — คำนวณ ROC หลาย period แล้ว WMA |
| formula | Special K = WMA(13-wk ROC,10) + WMA(26-wk ROC,15) + WMA(52-wk ROC,20) + WMA(104-wk ROC,30) |
| ref | https://www.investopedia.com/terms/p/pring-special-k.asp |

**Match BUY:** Special K > 0 และ rising  
**Match SELL:** Special K < 0 และ falling  
**File:** `api/services/indicators/trend/special_k.py`  
**AC:** `compute_special_k(bars)`, registered, pytest ผ่าน

---

#### IND-T-26 | Chande TrendScore | `trendscore`

| Field | Value |
|-------|-------|
| pandas-ta | custom: นับจำนวน SMA period ที่ close อยู่เหนือ |
| formula | TrendScore = Σ(1 if close > SMA(p)) for p in [20,50,75,100,125,150,175,200]; range 0–8 |
| ref | https://www.investopedia.com/terms/c/chande-trend-score.asp |

**Match BUY:** TrendScore ≥ 5  
**Match SELL:** TrendScore ≤ 3  
**File:** `api/services/indicators/trend/trendscore.py`  
**AC:** `compute_trendscore(bars)`, count logic ถูกต้อง, registered, pytest ผ่าน

---

#### IND-T-27 | Zero Lag MACD | `zlmacd`

| Field | Value |
|-------|-------|
| pandas-ta | custom: MACD ใช้ ZLEMA แทน EMA |
| formula | ZL-MACD = ZLEMA(12) − ZLEMA(26); Signal = EMA9(ZL-MACD) |
| ref | https://www.fmlabs.com/reference/default.htm?url=ZLEMA.htm |

**Match BUY:** ZL-MACD > Signal  
**Match SELL:** ZL-MACD < Signal  
**File:** `api/services/indicators/trend/zlmacd.py`  
**AC:** `compute_zlmacd(bars)`, registered, pytest ผ่าน

---

#### IND-T-28 | Trend Continuation Factor | `tcf`

| Field | Value |
|-------|-------|
| pandas-ta | custom |
| formula | TCF_plus = Σmax(close−close_prev, 0) N days; TCF_minus = Σmax(close_prev−close, 0) N days; ใช้ทั้งคู่ |
| ref | https://www.fmlabs.com/reference/default.htm?url=TCF.htm |

**Match BUY:** TCF_plus > TCF_minus  
**Match SELL:** TCF_minus > TCF_plus  
**File:** `api/services/indicators/trend/tcf.py`  
**AC:** `compute_tcf(bars, period=35)`, registered, pytest ผ่าน

---

#### IND-T-29 | Choppiness Index | `chop`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.chop(length=14)` → `CHOP_14_1_100` |
| formula | CHOP = 100 × log10(Σ(ATR1,N) / (HighN − LowN)) / log10(N) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:choppiness_index |

**Match BUY หรือ SELL:** CHOP < 38.2 (ตลาด trending ไม่ว่าทิศไหน — ใช้ร่วมกับ indicator อื่นยืนยันทิศ)  
**File:** `api/services/indicators/trend/chop.py`  
**AC:** `compute_chop(bars)` คืน value + matched=True เมื่อ trending, registered, pytest ผ่าน

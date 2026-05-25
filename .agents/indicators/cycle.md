# Cycle / Statistical Indicators — 13 Tasks

**assignee:** (ว่าง — ใครหยิบได้) | **priority:** low | **group:** cycle

ทุก task block กับ **Indicator Engine Infrastructure**

---

#### IND-C-01 | Correlation Coefficient | `correlation`

| Field | Value |
|-------|-------|
| pandas-ta | custom: pandas `.corr()` ระหว่าง XAUUSD กับ USD index หรือ price vs SMA |
| formula | r = Σ((x−x̄)(y−ȳ)) / sqrt(Σ(x−x̄)² × Σ(y−ȳ)²) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:correlation_coefficient |

**Match BUY:** r(price, SMA) > 0.7 (price strongly correlated with uptrend)  
**Match SELL:** r(price, SMA) < −0.7  
**File:** `api/services/indicators/cycle/correlation.py`  
**AC:** `compute_correlation(bars, period=20)`, Pearson r ถูกต้อง, registered, pytest ผ่าน

---

#### IND-C-02 | R-Squared | `r_squared`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.linreg(length=14, r=True)` → `LRr_14` |
| formula | R² = 1 − SS_res/SS_tot; สูง = price ตาม trend ชัดเจน |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:r_squared |

**Match BUY หรือ SELL:** R² > 0.75 (price trending strongly — ดูทิศจาก slope)  
**File:** `api/services/indicators/cycle/r_squared.py`  
**AC:** `compute_r_squared(bars, period=14)`, R² formula ถูกต้อง, registered, pytest ผ่าน

---

#### IND-C-03 | Linear Regression Slope | `linreg_slope`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.linreg(length=14, slope=True)` → `LRs_14` |
| formula | m = (NΣxy − ΣxΣy) / (NΣx² − (Σx)²); slope ของ best-fit line |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:linear_regression |

**Match BUY:** slope > 0  
**Match SELL:** slope < 0  
**File:** `api/services/indicators/cycle/linreg_slope.py`  
**AC:** `compute_linreg_slope(bars, period=14)`, slope calculation ถูกต้อง, registered, pytest ผ่าน

---

#### IND-C-04 | Kaufman Efficiency Ratio | `kaufman_er`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.er(length=10)` → `ER_10` |
| formula | ER = |Close − Close_N| / Σ|Close_i − Close_i-1|; range 0–1 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:kaufman_s_adaptive_moving_average |

**Match BUY:** ER > 0.6 AND price rising (highly efficient upward movement)  
**Match SELL:** ER > 0.6 AND price falling  
**File:** `api/services/indicators/cycle/kaufman_er.py`  
**AC:** `compute_kaufman_er(bars, period=10)`, range 0–1, registered, pytest ผ่าน

---

#### IND-C-05 | Price Relative / Relative Strength | `price_relative`

| Field | Value |
|-------|-------|
| pandas-ta | custom: XAUUSD / XAUUSD_SMA(50) หรือเทียบกับ benchmark |
| formula | RS = Close / SMA(Close, 50) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:price_relative |

**Match BUY:** RS > 1 (outperforming own average)  
**Match SELL:** RS < 1  
**File:** `api/services/indicators/cycle/price_relative.py`  
**AC:** `compute_price_relative(bars, period=50)`, ratio ถูกต้อง, registered, pytest ผ่าน

---

#### IND-C-06 | Rahul Mohindar Oscillator | `rmo`

| Field | Value |
|-------|-------|
| pandas-ta | custom: multi-swing smoothed oscillator |
| formula | SwingTrd1=SMA(2C−H−L,2)×0.2; SwingTrd2=SMA(SwingTrd1,3)×0.2; MTM=SMA(2C−H−L,n)×0.2 |
| ref | https://www.investopedia.com/terms/r/rmo-oscillator.asp |

**Match BUY:** RMO > 0 (bullish swing trend)  
**Match SELL:** RMO < 0  
**File:** `api/services/indicators/cycle/rmo.py`  
**AC:** `compute_rmo(bars)`, multi-swing calculation ถูกต้อง, registered, pytest ผ่าน

---

#### IND-C-07 | VIDYA (Chande Variable Index Dynamic Average) | `vidya`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.vidya(length=14)` → `VIDYA_14` |
| formula | VIDYA = k×CMO/100 × Close + (1 − k×CMO/100) × VIDYA_prev; k = 2/(period+1) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:variable_index_dynamic_average_vidya |

**Match BUY:** close > VIDYA  
**Match SELL:** close < VIDYA  
**File:** `api/services/indicators/cycle/vidya.py`  
**AC:** `compute_vidya(bars, period=14)`, adaptive alpha ถูกต้อง, registered, pytest ผ่าน

---

#### IND-C-08 | RAVI (Range Action Verification Index) | `ravi`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.ravi(fast=7, slow=65)` → `RAVI_7_65` |
| formula | RAVI = |SMA(7) − SMA(65)| / SMA(65) × 100 |
| ref | https://www.investopedia.com/terms/r/ravi.asp |

**Match BUY:** RAVI > 3% (trending market) AND price > SMA(65)  
**Match SELL:** RAVI > 3% AND price < SMA(65)  
**File:** `api/services/indicators/cycle/ravi.py`  
**AC:** `compute_ravi(bars)`, % gap ถูกต้อง, registered, pytest ผ่าน

---

#### IND-C-09 | Detrended Price Oscillator (Cycle) | `dpo_cycle`

| Field | Value |
|-------|-------|
| pandas-ta | ใช้ `df.ta.dpo(length=20)` — เหมือน IND-M-23 แต่ใช้เพื่อหา cycle length |
| formula | DPO = Close − SMA(N, shift=N/2+1); peak-to-peak distance = cycle period |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:detrended_price_osci |

**Match BUY:** DPO crossing up from below 0  
**Match SELL:** DPO crossing down from above 0  
**File:** `api/services/indicators/cycle/dpo_cycle.py`  
**AC:** `compute_dpo_cycle(bars)`, zero-cross detection ถูกต้อง, registered, pytest ผ่าน

---

#### IND-C-10 | Standard Error Bands (Cycle) | skipped — อยู่ใน sr แล้ว (IND-S-17)

#### IND-C-10 | Kurtosis Indicator | `kurtosis`

| Field | Value |
|-------|-------|
| pandas-ta | custom: scipy.stats.kurtosis ของ rolling returns |
| formula | Kurt = E[(X−μ)⁴] / σ⁴ − 3 (excess kurtosis); สูง = fat tail / ราคากระโดด |
| ref | https://www.investopedia.com/terms/k/kurtosis.asp |

**Match BUY หรือ SELL:** kurtosis > 3 (excess positive kurtosis) — ความเสี่ยง tail event สูง ใช้เป็น risk signal  
**File:** `api/services/indicators/cycle/kurtosis.py`  
**AC:** `compute_kurtosis(bars, period=20)`, excess kurtosis ถูกต้อง, registered, pytest ผ่าน

---

#### IND-C-11 | Pring KST (Cycle context) | skipped — อยู่ใน momentum แล้ว (IND-M-16)

#### IND-C-11 | StochRSI (Cycle) | skipped — อยู่ใน momentum แล้ว (IND-M-03)

#### IND-C-11 | Historical Volatility Percentile | `hv_percentile`

| Field | Value |
|-------|-------|
| pandas-ta | custom: percentile rank ของ HV ใน rolling 252-day window |
| formula | HV_Pct = rank(HV_current, HV_252_days) / 252 × 100 |
| ref | https://www.investopedia.com/terms/h/historicalvolatility.asp |

**Match BUY หรือ SELL:** HV_Pct < 25 (low vol regime = breakout setup likely)  
**File:** `api/services/indicators/cycle/hv_percentile.py`  
**AC:** `compute_hv_percentile(bars)`, percentile rank ถูกต้อง, registered, pytest ผ่าน

---

#### IND-C-12 | Coppock Curve (Cycle) | skipped — อยู่ใน momentum (IND-M-15)

#### IND-C-12 | Z-Score Indicator | `zscore`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.zscore(length=20)` → `ZS_20` |
| formula | Z = (Close − SMA(N)) / StdDev(N) |
| ref | https://www.investopedia.com/terms/z/zscore.asp |

**Match BUY:** Z-Score < −2 (ราคาต่ำกว่า mean ≥ 2σ = mean reversion opportunity up)  
**Match SELL:** Z-Score > +2  
**File:** `api/services/indicators/cycle/zscore.py`  
**AC:** `compute_zscore(bars, period=20)`, Z formula ถูกต้อง, registered, pytest ผ่าน

---

#### IND-C-13 | Chande Variable Index Dynamic Average (cycle) | skipped — IND-C-07 แล้ว

#### IND-C-13 | Hurst Exponent | `hurst`

| Field | Value |
|-------|-------|
| pandas-ta | custom: R/S analysis หรือ DFA method |
| formula | H = log(R/S) / log(N); H > 0.5 = trending; H < 0.5 = mean-reverting; H ≈ 0.5 = random |
| ref | https://www.investopedia.com/terms/h/hurst-exponent.asp |

**Match BUY:** H > 0.6 AND price rising (persistent trend up)  
**Match SELL:** H > 0.6 AND price falling  
**File:** `api/services/indicators/cycle/hurst.py`  
**AC:** `compute_hurst(bars, period=100)`, H range 0–1, >0.5 = trending ถูกต้อง, registered, pytest ผ่าน

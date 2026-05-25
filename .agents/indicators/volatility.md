# Volatility Indicators — 15 Tasks

**assignee:** claude | **status:** done | **priority:** low | **group:** volatility

ทุก task block กับ **Indicator Engine Infrastructure**

---

#### IND-X-01 | Bollinger Bands | `bbands`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.bbands(length=20, std=2)` → `BBL_20_2.0`, `BBM_20_2.0`, `BBU_20_2.0` |
| formula | BB_upper = SMA(20) + 2×StdDev; BB_lower = SMA(20) − 2×StdDev |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:bollinger_bands |

**Match BUY:** close < BBL (ราคาใต้ lower band = oversold)  
**Match SELL:** close > BBU (ราคาเหนือ upper band = overbought)  
**File:** `api/services/indicators/volatility/bbands.py`  
**AC:** `compute_bbands(bars, period=20, std=2)`, registered, pytest ผ่าน

---

#### IND-X-02 | Bollinger BandWidth | `bbw`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.bbands()` แล้วดึง `BBB_20_2.0` column |
| formula | BBW = (BBU − BBL) / BBM × 100 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:bollinger_band_width |

**Match BUY หรือ SELL:** BBW < percentile(BBW, 10, lookback=252) — squeeze = กำลัง coil ก่อน breakout  
**File:** `api/services/indicators/volatility/bbw.py`  
**AC:** `compute_bbw(bars)`, squeeze detection ถูกต้อง, registered, pytest ผ่าน

---

#### IND-X-03 | Average True Range | `atr`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.atr(length=14)` → `ATRr_14` |
| formula | TR = max(H−L, |H−Close_prev|, |L−Close_prev|); ATR = EMA(TR, 14) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:average_true_range_atr |

**Match BUY หรือ SELL:** ATR > SMA(ATR, 20) (volatility ขยาย = good breakout environment)  
**File:** `api/services/indicators/volatility/atr.py`  
**AC:** `compute_atr(bars, period=14)`, TR formula ถูกต้อง, registered, pytest ผ่าน

---

#### IND-X-04 | Keltner Channels | `kc`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.kc(length=20, scalar=2)` → `KCLe_20_2`, `KCBe_20_2`, `KCUe_20_2` |
| formula | KC_upper = EMA(20) + 2×ATR(10); KC_lower = EMA(20) − 2×ATR(10) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:keltner_channels |

**Match BUY:** close < KCLe (ราคาต่ำกว่า lower channel)  
**Match SELL:** close > KCUe  
**File:** `api/services/indicators/volatility/kc.py`  
**AC:** `compute_kc(bars)`, registered, pytest ผ่าน

---

#### IND-X-05 | Donchian Channel | `donchian`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.donchian(lower_length=20, upper_length=20)` → `DCL_20_20`, `DCM_20_20`, `DCU_20_20` |
| formula | DCU = max(High, N); DCL = min(Low, N); DCM = (DCU+DCL)/2 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:donchian_channels |

**Match BUY:** close breaks above DCU (20-period high breakout)  
**Match SELL:** close breaks below DCL  
**File:** `api/services/indicators/volatility/donchian.py`  
**AC:** `compute_donchian(bars, period=20)`, breakout detection, registered, pytest ผ่าน

---

#### IND-X-06 | Standard Deviation | `stdev`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.stdev(length=20)` → `STDEV_20` |
| formula | σ = sqrt(Σ(Close − SMA)² / N) |
| ref | https://www.investopedia.com/terms/s/standarddeviation.asp |

**Match BUY หรือ SELL:** StdDev > SMA(StdDev, 20) (volatility สูงกว่าปกติ = volatile environment)  
**File:** `api/services/indicators/volatility/stdev.py`  
**AC:** `compute_stdev(bars, period=20)`, registered, pytest ผ่าน

---

#### IND-X-07 | Chaikin Volatility | `chaikin_vol`

| Field | Value |
|-------|-------|
| pandas-ta | custom |
| formula | ChaikinVol = ROC(EMA(H−L, 10), 10) × 100 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:chaikin_volatility |

**Match BUY หรือ SELL:** ChaikinVol > 0 (range กำลังขยาย — ร่วมกับ direction indicator)  
**File:** `api/services/indicators/volatility/chaikin_vol.py`  
**AC:** `compute_chaikin_vol(bars)`, registered, pytest ผ่าน

---

#### IND-X-08 | STARC Bands | `starc`

| Field | Value |
|-------|-------|
| pandas-ta | custom: SMA(5) ± ATR(15) × 1.33 |
| formula | STARC_upper = SMA(5) + ATR(15) × 1.33; STARC_lower = SMA(5) − ATR(15) × 1.33 |
| ref | https://www.investopedia.com/terms/s/starc.asp |

**Match BUY:** close ≤ STARC_lower  
**Match SELL:** close ≥ STARC_upper  
**File:** `api/services/indicators/volatility/starc.py`  
**AC:** `compute_starc(bars)`, ATR multiplier ถูกต้อง, registered, pytest ผ่าน

---

#### IND-X-09 | Average Daily Range | `adr`

| Field | Value |
|-------|-------|
| pandas-ta | custom: SMA(H−L, 14) จาก D timeframe |
| formula | ADR = mean(High_D − Low_D, 14 days) |
| ref | https://www.investopedia.com/terms/a/average-daily-range.asp |

**Match BUY หรือ SELL:** (Close − Open) / ADR > 0.5 (ราคาขยับเกิน 50% ของ ADR แล้ว = momentum day)  
**File:** `api/services/indicators/volatility/adr.py`  
**AC:** `compute_adr(bars_daily)` ใช้ D timeframe, registered, pytest ผ่าน

---

#### IND-X-10 | Historical Volatility | `hv`

| Field | Value |
|-------|-------|
| pandas-ta | custom: annualised StdDev ของ log return |
| formula | HV = StdDev(ln(Close/Close_prev), 20) × sqrt(252) × 100 |
| ref | https://www.investopedia.com/terms/h/historicalvolatility.asp |

**Match BUY หรือ SELL:** HV < percentile(HV, 25, 252) — low vol environment = potential breakout  
**File:** `api/services/indicators/volatility/hv.py`  
**AC:** `compute_hv(bars, period=20)`, annualization ถูกต้อง, registered, pytest ผ่าน

---

#### IND-X-11 | Ulcer Index | `ulcer`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.ui(length=14)` → `UI_14` |
| formula | UI = sqrt(Σ(drawdown_from_peak²) / N); drawdown = (Close − max_close_N) / max_close_N × 100 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:ulcer_index |

**Match BUY:** UI กำลังลดลง (ความเจ็บปวดจาก drawdown กำลังลด = recovery)  
**Match SELL:** ไม่ใช้ direct signal — ใช้เป็น risk indicator  
**File:** `api/services/indicators/volatility/ulcer.py`  
**AC:** `compute_ulcer(bars)`, drawdown calc ถูกต้อง, registered, pytest ผ่าน

---

#### IND-X-12 | TTM Squeeze | `ttm_squeeze`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.squeeze(bb_length=20, bb_std=2, kc_length=20, kc_scalar=1.5)` → `SQZ_ON`, `SQZ_OFF`, `SQZPRO_20_2.0_20_1.5` |
| formula | Squeeze ON = BBands อยู่ใน Keltner Channels; Momentum = linreg(Close − avg(SMA+midDC), 20) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:ttm_squeeze |

**Match BUY:** SQZ_OFF AND momentum > 0 (squeeze ปล่อยขึ้น)  
**Match SELL:** SQZ_OFF AND momentum < 0  
**File:** `api/services/indicators/volatility/ttm_squeeze.py`  
**AC:** `compute_ttm_squeeze(bars)`, squeeze ON/OFF + momentum direction ถูกต้อง, registered, pytest ผ่าน

---

#### IND-X-13 | Percent B | `pctb`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.bbands()` ดึง `BBP_20_2.0` column |
| formula | %B = (Close − BBL) / (BBU − BBL) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:percent_b_pb |

**Match BUY:** %B < 0 (ราคาต่ำกว่า lower band)  
**Match SELL:** %B > 1 (ราคาสูงกว่า upper band)  
**File:** `api/services/indicators/volatility/pctb.py`  
**AC:** `compute_pctb(bars)`, range คำนวณถูกต้อง, registered, pytest ผ่าน

---

#### IND-X-14 | Average Daily Range % | `adr_pct`

| Field | Value |
|-------|-------|
| pandas-ta | custom: extension จาก IND-X-09 เป็น % |
| formula | ADR% = ADR / Close × 100 |
| ref | https://www.investopedia.com/terms/a/average-daily-range.asp |

**Match BUY หรือ SELL:** ADR% ช่วย calibrate SL/TP เป็นหลัก — matched=True ถ้า trade SL < 1×ADR  
**File:** `api/services/indicators/volatility/adr_pct.py`  
**AC:** `compute_adr_pct(bars)`, registered, pytest ผ่าน

---

#### IND-X-15 | Mass Index (Volatility Use) | skipped — อยู่ใน momentum แล้ว (IND-M-29)

#### IND-X-15 | Linear Regression Channel | `linreg_channel`

| Field | Value |
|-------|-------|
| pandas-ta | custom: `df.ta.linreg()` + ± 2×StdErr |
| formula | Channel = LinReg(Close,N) ± 2 × standard_error(residuals) |
| ref | https://www.investopedia.com/terms/r/regressionchannel.asp |

**Match BUY:** close ≤ lower channel  
**Match SELL:** close ≥ upper channel  
**File:** `api/services/indicators/volatility/linreg_channel.py`  
**AC:** `compute_linreg_channel(bars, period=20)`, StdErr calculation ถูกต้อง, registered, pytest ผ่าน

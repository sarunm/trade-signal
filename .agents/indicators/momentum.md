# Momentum / Oscillator Indicators — 39 Tasks

**assignee:** codex | **status:** done | **priority:** normal | **group:** momentum

ทุก task ใน file นี้ block อยู่กับ **Indicator Engine Infrastructure** (ต้องทำก่อน)

---

#### IND-M-01 | Relative Strength Index | `rsi`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.rsi(length=14)` → `RSI_14` |
| formula | RSI = 100 − (100 / (1 + RS)); RS = avg_gain / avg_loss over N periods |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:relative_strength_index_rsi |

**Match BUY:** RSI < 30 (oversold) ที่ entry bar  
**Match SELL:** RSI > 70 (overbought) ที่ entry bar  
**File:** `api/services/indicators/momentum/rsi.py`  
**AC:** `compute_rsi(bars, period=14)`, OB/OS threshold ถูกต้อง, registered, pytest ผ่าน

---

#### IND-M-02 | Stochastic Oscillator | `stoch`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.stoch(k=14, d=3, smooth_k=3)` → `STOCHk_14_3_3`, `STOCHd_14_3_3` |
| formula | %K = (Close − Low_N) / (High_N − Low_N) × 100; %D = SMA3(%K) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:stochastic_oscillator_fast_slow_and_full |

**Match BUY:** %K < 20 (oversold)  
**Match SELL:** %K > 80 (overbought)  
**File:** `api/services/indicators/momentum/stoch.py`  
**AC:** `compute_stoch(bars)`, OB/OS ถูกต้อง, registered, pytest ผ่าน

---

#### IND-M-03 | Stochastic RSI | `stochrsi`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.stochrsi(length=14, rsi_length=14, k=3, d=3)` → `STOCHRSIk_14_14_3_3` |
| formula | StochRSI = (RSI − min(RSI,N)) / (max(RSI,N) − min(RSI,N)) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:stochrsi |

**Match BUY:** StochRSI_k < 0.2  
**Match SELL:** StochRSI_k > 0.8  
**File:** `api/services/indicators/momentum/stochrsi.py`  
**AC:** `compute_stochrsi(bars)`, range 0–1, registered, pytest ผ่าน

---

#### IND-M-04 | Stochastic Momentum Index | `smi`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.smi(k=5, d=3, signal=3)` → `SMI_5_3_3` |
| formula | SMI = (Close − midpoint) / (0.5 × H-L range) × 100; double-smoothed; range ±100 |
| ref | https://www.investopedia.com/terms/s/stochastic-momentum-index-smi.asp |

**Match BUY:** SMI < −40  
**Match SELL:** SMI > +40  
**File:** `api/services/indicators/momentum/smi.py`  
**AC:** `compute_smi(bars)`, range ±100, registered, pytest ผ่าน

---

#### IND-M-05 | Williams %R | `willr`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.willr(length=14)` → `WILLR_14` |
| formula | %R = (High_N − Close) / (High_N − Low_N) × −100; range −100 ถึง 0 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:williams_r |

**Match BUY:** %R < −80 (oversold)  
**Match SELL:** %R > −20 (overbought)  
**File:** `api/services/indicators/momentum/willr.py`  
**AC:** `compute_willr(bars)`, threshold ถูกต้อง, registered, pytest ผ่าน

---

#### IND-M-06 | Commodity Channel Index | `cci`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.cci(length=20)` → `CCI_20_0.015` |
| formula | CCI = (TP − SMA(TP,N)) / (0.015 × MeanDev); TP = (H+L+C)/3 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:commodity_channel_index_cci |

**Match BUY:** CCI < −100 (oversold)  
**Match SELL:** CCI > +100 (overbought)  
**File:** `api/services/indicators/momentum/cci.py`  
**AC:** `compute_cci(bars, period=20)`, registered, pytest ผ่าน

---

#### IND-M-07 | Momentum | `mom`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.mom(length=10)` → `MOM_10` |
| formula | MOM(N) = Close − Close_N_periods_ago |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:momentum |

**Match BUY:** MOM > 0  
**Match SELL:** MOM < 0  
**File:** `api/services/indicators/momentum/mom.py`  
**AC:** `compute_mom(bars, period=10)`, registered, pytest ผ่าน

---

#### IND-M-08 | Rate of Change | `roc`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.roc(length=10)` → `ROC_10` |
| formula | ROC = (Close − Close_N) / Close_N × 100 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:rate_of_change_roc_and_momentum |

**Match BUY:** ROC > 0  
**Match SELL:** ROC < 0  
**File:** `api/services/indicators/momentum/roc.py`  
**AC:** `compute_roc(bars, period=10)`, registered, pytest ผ่าน

---

#### IND-M-09 | Ultimate Oscillator | `uo`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.uo(fast=7, medium=14, slow=28)` → `UO_7_14_28` |
| formula | UO = 100 × [4×BP7/(4×TR7) + 2×BP14/(2×TR14) + BP28/TR28] / 7; BP=Close−min(Low,Close_prev) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:ultimate_oscillator |

**Match BUY:** UO < 30  
**Match SELL:** UO > 70  
**File:** `api/services/indicators/momentum/uo.py`  
**AC:** `compute_uo(bars)`, registered, pytest ผ่าน

---

#### IND-M-10 | DeMarker Indicator | `demarker`

| Field | Value |
|-------|-------|
| pandas-ta | custom — pandas-ta ไม่มี |
| formula | DeMax=max(High−High_prev,0); DeMin=max(Low_prev−Low,0); DeM=SMA(DeMax,N)/(SMA(DeMax,N)+SMA(DeMin,N)) |
| ref | https://www.investopedia.com/terms/d/demarkerindicator.asp |

**Match BUY:** DeM < 0.3  
**Match SELL:** DeM > 0.7  
**File:** `api/services/indicators/momentum/demarker.py`  
**AC:** `compute_demarker(bars, period=14)`, range 0–1, registered, pytest ผ่าน

---

#### IND-M-11 | Awesome Oscillator | `ao`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.ao(fast=5, slow=34)` → `AO_5_34` |
| formula | AO = SMA(midpoint, 5) − SMA(midpoint, 34); midpoint = (High+Low)/2 |
| ref | https://www.investopedia.com/terms/a/awesome-oscillator.asp |

**Match BUY:** AO > 0 (above zero line)  
**Match SELL:** AO < 0 (below zero line)  
**File:** `api/services/indicators/momentum/ao.py`  
**AC:** `compute_ao(bars)`, registered, pytest ผ่าน

---

#### IND-M-12 | Acceleration/Deceleration | `ac`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.ac(fast=5, slow=34, signal=5)` → `AC_5_34_5` |
| formula | AC = AO − SMA(AO, 5) |
| ref | https://www.investopedia.com/terms/a/ac.asp |

**Match BUY:** AC > 0 (momentum กำลัง accelerate ขึ้น)  
**Match SELL:** AC < 0  
**File:** `api/services/indicators/momentum/ac.py`  
**AC:** `compute_ac(bars)`, registered, pytest ผ่าน

---

#### IND-M-13 | TRIX | `trix`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.trix(length=18, signal=9)` → `TRIX_18_9`, `TRIXs_18_9` |
| formula | TRIX = %ROC(EMA(EMA(EMA(Close,N),N),N)) ; 1-period ROC ของ triple-smoothed EMA |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:trix |

**Match BUY:** TRIX > 0 หรือ TRIX crosses above signal  
**Match SELL:** TRIX < 0 หรือ TRIX crosses below signal  
**File:** `api/services/indicators/momentum/trix.py`  
**AC:** `compute_trix(bars)`, registered, pytest ผ่าน

---

#### IND-M-14 | True Strength Index | `tsi`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.tsi(fast=13, slow=25, signal=13)` → `TSI_25_13_13` |
| formula | TSI = 100 × EMA(EMA(PC,fast),slow) / EMA(EMA(|PC|,fast),slow); PC=Close−Close_prev |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:true_strength_index |

**Match BUY:** TSI > 0  
**Match SELL:** TSI < 0  
**File:** `api/services/indicators/momentum/tsi.py`  
**AC:** `compute_tsi(bars)`, registered, pytest ผ่าน

---

#### IND-M-15 | Coppock Curve | `coppock`

| Field | Value |
|-------|-------|
| pandas-ta | custom — `df.ta.cg()` ไม่ใช่ Coppock; ใช้ WMA ของ ROC |
| formula | Coppock = WMA(ROC(11) + ROC(14), 10) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:coppock_curve |

**Match BUY:** Coppock crosses above 0 (ใน 3 bar ล่าสุด)  
**Match SELL:** Coppock crosses below 0  
**File:** `api/services/indicators/momentum/coppock.py`  
**AC:** `compute_coppock(bars)`, crossover detection ถูกต้อง, registered, pytest ผ่าน

---

#### IND-M-16 | Know Sure Thing | `kst`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.kst(roc1=10, roc2=13, roc3=14, roc4=15)` → `KST_10_13_14_15_10_13_14_15_9` |
| formula | KST = SMA(ROC10,10)×1 + SMA(ROC13,13)×2 + SMA(ROC14,14)×3 + SMA(ROC15,15)×4 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:know_sure_thing_kst |

**Match BUY:** KST > Signal line  
**Match SELL:** KST < Signal line  
**File:** `api/services/indicators/momentum/kst.py`  
**AC:** `compute_kst(bars)`, registered, pytest ผ่าน

---

#### IND-M-17 | Price Momentum Oscillator | `pmo`

| Field | Value |
|-------|-------|
| pandas-ta | custom: double-smoothed ROC |
| formula | PMO = EMA(EMA(ROC(1)×10, 35), 20); Signal = EMA(PMO, 10) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:price_momentum_oscillator_pmo |

**Match BUY:** PMO > Signal  
**Match SELL:** PMO < Signal  
**File:** `api/services/indicators/momentum/pmo.py`  
**AC:** `compute_pmo(bars)`, registered, pytest ผ่าน

---

#### IND-M-18 | Chande Momentum Oscillator | `cmo`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.cmo(length=9)` → `CMO_9` |
| formula | CMO = (Σ(up_close) − Σ(down_close)) / (Σ(up_close) + Σ(down_close)) × 100; range ±100 |
| ref | https://www.investopedia.com/terms/c/chandemomentumoscillator.asp |

**Match BUY:** CMO < −50 (oversold)  
**Match SELL:** CMO > +50 (overbought)  
**File:** `api/services/indicators/momentum/cmo.py`  
**AC:** `compute_cmo(bars, period=9)`, range ±100, registered, pytest ผ่าน

---

#### IND-M-19 | Relative Momentum Index | `rmi`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.rmi(length=20, scalar=100, drift=5)` → `RMI_20_5` |
| formula | RMI = RSI ที่ใช้ momentum(N) แทน 1-period change |
| ref | https://www.investopedia.com/terms/r/relative-momentum-index.asp |

**Match BUY:** RMI < 30  
**Match SELL:** RMI > 70  
**File:** `api/services/indicators/momentum/rmi.py`  
**AC:** `compute_rmi(bars)`, registered, pytest ผ่าน

---

#### IND-M-20 | Elder-Ray Index | `elder_ray`

| Field | Value |
|-------|-------|
| pandas-ta | custom: `df.ta.ema(13)` แล้วคำนวณ Bull/Bear Power |
| formula | Bull Power = High − EMA(13); Bear Power = Low − EMA(13) |
| ref | https://www.investopedia.com/terms/e/elderray.asp |

**Match BUY:** Bear Power < 0 แต่กำลังเพิ่มขึ้น (approaching 0)  
**Match SELL:** Bull Power > 0 แต่กำลังลดลง (approaching 0)  
**File:** `api/services/indicators/momentum/elder_ray.py`  
**AC:** `compute_elder_ray(bars)`, bull/bear power ถูกต้อง, registered, pytest ผ่าน

---

#### IND-M-21 | Force Index | `force_index`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.efi(length=13)` → `EFI_13` |
| formula | FI(1) = (Close − Close_prev) × Volume; FI(N) = EMA(FI(1), N) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:force_index |

**Match BUY:** EFI_13 > 0  
**Match SELL:** EFI_13 < 0  
**File:** `api/services/indicators/momentum/force_index.py`  
**AC:** `compute_force_index(bars, period=13)`, registered, pytest ผ่าน

---

#### IND-M-22 | Balance of Power | `bop`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.bop(scalar=1)` → `BOP` |
| formula | BOP = (Close − Open) / (High − Low) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:balance_of_power |

**Match BUY:** BOP > 0 (buyers dominate)  
**Match SELL:** BOP < 0 (sellers dominate)  
**File:** `api/services/indicators/momentum/bop.py`  
**AC:** `compute_bop(bars)`, registered, pytest ผ่าน

---

#### IND-M-23 | Detrended Price Oscillator | `dpo`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.dpo(length=20)` → `DPO_20` |
| formula | DPO = Close − SMA(N) shifted back (N/2 + 1) periods |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:detrended_price_osci |

**Match BUY:** DPO > 0  
**Match SELL:** DPO < 0  
**File:** `api/services/indicators/momentum/dpo.py`  
**AC:** `compute_dpo(bars, period=20)`, registered, pytest ผ่าน

---

#### IND-M-24 | Ehlers Fisher Transform | `fisher`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.fisher(length=9)` → `FISHERT_9_1`, `FISHERTs_9_1` |
| formula | Value=(H+L)/2 normalized; Fisher=0.5×ln((1+Value)/(1−Value)) |
| ref | https://www.investopedia.com/terms/f/fisher-transform.asp |

**Match BUY:** Fisher crosses above 0 หรือ Fisher > 0  
**Match SELL:** Fisher crosses below 0 หรือ Fisher < 0  
**File:** `api/services/indicators/momentum/fisher.py`  
**AC:** `compute_fisher(bars)`, registered, pytest ผ่าน

---

#### IND-M-25 | Relative Vigor Index | `rvi`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.rvgi(length=14, swma_length=4)` → `RVGI_14_4`, `RVGIs_14_4` |
| formula | RVI = EMA(Close−Open) / EMA(High−Low); Signal = symmetric WMA of RVI |
| ref | https://www.investopedia.com/terms/r/relative_vigor_index.asp |

**Match BUY:** RVI > Signal  
**Match SELL:** RVI < Signal  
**File:** `api/services/indicators/momentum/rvi.py`  
**AC:** `compute_rvi(bars)`, registered, pytest ผ่าน

---

#### IND-M-26 | Ehlers Laguerre RSI | `laguerre_rsi`

| Field | Value |
|-------|-------|
| pandas-ta | custom — ใช้ Laguerre filter (gamma=0.5) |
| formula | L0=α×Close+(1−α)×L0_prev; L1=(1−α)×L0_prev; ... RSI=ΣPos/(ΣPos+ΣNeg) |
| ref | https://www.mesasoftware.com/papers/LAGUERRE.pdf |

**Match BUY:** Laguerre RSI < 0.2  
**Match SELL:** Laguerre RSI > 0.8  
**File:** `api/services/indicators/momentum/laguerre_rsi.py`  
**AC:** `compute_laguerre_rsi(bars, gamma=0.5)`, range 0–1, registered, pytest ผ่าน

---

#### IND-M-27 | Double Stochastic Oscillator | `double_stoch`

| Field | Value |
|-------|-------|
| pandas-ta | custom: Stochastic ของ Stochastic |
| formula | DS = Stochastic(%K ของ Stochastic(14,3), period=3) |
| ref | https://www.fmlabs.com/reference/default.htm?url=DSS.htm |

**Match BUY:** DS < 20  
**Match SELL:** DS > 80  
**File:** `api/services/indicators/momentum/double_stoch.py`  
**AC:** `compute_double_stoch(bars)`, registered, pytest ผ่าน

---

#### IND-M-28 | ConnorsRSI | `crsi`

| Field | Value |
|-------|-------|
| pandas-ta | custom: RSI(3) + RSI(streak, 2) + PercentRank(ROC, 100) |
| formula | CRSI = (RSI3 + StreakRSI2 + PercentRank100) / 3 |
| ref | https://www.multicharts.com/trading-software/index.php/ConnorsRSI |

**Match BUY:** CRSI < 20  
**Match SELL:** CRSI > 80  
**File:** `api/services/indicators/momentum/crsi.py`  
**AC:** `compute_crsi(bars)`, 3 components ถูกต้อง, registered, pytest ผ่าน

---

#### IND-M-29 | Mass Index | `mass_index`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.massi(fast=9, slow=25)` → `MASSI_9_25` |
| formula | MI = Σ(EMA9(H−L) / EMA9(EMA9(H−L)), 25) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:mass_index |

**Match BUY หรือ SELL:** MI > 27 แล้วลงมาต่ำกว่า 26.5 (reversal bulge) — ทิศขึ้นกับ indicator อื่น  
**File:** `api/services/indicators/momentum/mass_index.py`  
**AC:** `compute_mass_index(bars)`, reversal bulge detection ถูกต้อง, registered, pytest ผ่าน

---

#### IND-M-30 | Choppiness Index (Momentum Use) | skipped — อยู่ใน trend แล้ว (IND-T-29)

---

#### IND-M-30 | Polarized Fractal Efficiency | `pfe`

| Field | Value |
|-------|-------|
| pandas-ta | custom |
| formula | PFE = sign(Close−Close_N) × 100 × (Close−Close_N) / Σ(sqrt(1+(C_i−C_prev)²), N) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:polarized_fractal_efficiency |

**Match BUY:** PFE > 50 (เดินขึ้นอย่างมีประสิทธิภาพ)  
**Match SELL:** PFE < −50  
**File:** `api/services/indicators/momentum/pfe.py`  
**AC:** `compute_pfe(bars, period=10)`, registered, pytest ผ่าน

---

#### IND-M-31 | Disparity Index | `disparity`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.disparity(length=14)` → `DISP_14` |
| formula | DI = (Close − SMA(N)) / SMA(N) × 100 |
| ref | https://www.investopedia.com/terms/d/disparityindex.asp |

**Match BUY:** DI < −2 (ราคาต่ำกว่า MA มาก = potential reversal up)  
**Match SELL:** DI > +2  
**File:** `api/services/indicators/momentum/disparity.py`  
**AC:** `compute_disparity(bars, period=14)`, registered, pytest ผ่าน

---

#### IND-M-32 | Inertia Indicator | `inertia`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.inertia(length=14, rvi_length=14, scalar=100)` → `INERTIA_14_14` |
| formula | Inertia = linear regression ของ RVI(N) ทำ smooth |
| ref | https://library.tradingtechnologies.com/trade/chrt-ti-inertia.html |

**Match BUY:** Inertia > 0  
**Match SELL:** Inertia < 0  
**File:** `api/services/indicators/momentum/inertia.py`  
**AC:** `compute_inertia(bars)`, registered, pytest ผ่าน

---

#### IND-M-33 | Trend Intensity Index | `tti`

| Field | Value |
|-------|-------|
| pandas-ta | custom |
| formula | TII = (count ของ close เหนือ SMA(N) ใน M bars) / M × 100 |
| ref | https://www.fmlabs.com/reference/default.htm?url=TII.htm |

**Match BUY:** TII > 80 (ราคาอยู่เหนือ MA เป็นส่วนใหญ่)  
**Match SELL:** TII < 20  
**File:** `api/services/indicators/momentum/tti.py`  
**AC:** `compute_tti(bars)`, count ratio ถูกต้อง, registered, pytest ผ่าน

---

#### IND-M-34 | Elliott Wave Oscillator | `ewo`

| Field | Value |
|-------|-------|
| pandas-ta | custom: SMA(5) − SMA(35) ของ (H+L)/2 |
| formula | EWO = SMA(midpoint, 5) − SMA(midpoint, 35) |
| ref | https://www.investopedia.com/terms/e/elliott-wave-theory.asp |

**Match BUY:** EWO > 0  
**Match SELL:** EWO < 0  
**File:** `api/services/indicators/momentum/ewo.py`  
**AC:** `compute_ewo(bars)`, registered, pytest ผ่าน

---

#### IND-M-35 | Gator Oscillator | `gator`

| Field | Value |
|-------|-------|
| pandas-ta | custom: ใช้ Alligator แล้วคำนวณ histogram ของส่วนต่าง |
| formula | Gator Upper = |Jaw − Teeth|; Gator Lower = −|Teeth − Lips| |
| ref | https://www.investopedia.com/terms/g/gator-oscillator.asp |

**Match BUY:** Gator bars กำลังขยายตัว (alligator กำลัง "กิน") และ AO > 0  
**Match SELL:** Gator expanding และ AO < 0  
**File:** `api/services/indicators/momentum/gator.py`  
**AC:** `compute_gator(bars)`, upper/lower bars ถูกต้อง, registered, pytest ผ่าน

---

#### IND-M-36 | QQE (Quantitative Qualitative Estimation) | `qqe`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.qqe(length=14, smooth=5, factor=4.236)` → `QQE_14_5_4.236` |
| formula | RSI smooth → ATR ของ RSI → trailing QQE level; คล้าย RSI แต่มี dynamic band |
| ref | https://www.prorealcode.com/prorealtime-indicators/qqe-quantitative-qualitative-estimation/ |

**Match BUY:** RSI_MA > QQE trailing level (bullish cross)  
**Match SELL:** RSI_MA < QQE trailing level  
**File:** `api/services/indicators/momentum/qqe.py`  
**AC:** `compute_qqe(bars)`, registered, pytest ผ่าน

---

#### IND-M-37 | Chande Dynamic Momentum Index | `cdmi`

| Field | Value |
|-------|-------|
| pandas-ta | custom: RSI period ปรับตาม volatility |
| formula | period = 14 × (StdDev_5 / StdDev_10); clamped 5–30 |
| ref | https://www.investopedia.com/terms/c/chande-dynamic-momentum-index.asp |

**Match BUY:** CDMI < 30  
**Match SELL:** CDMI > 70  
**File:** `api/services/indicators/momentum/cdmi.py`  
**AC:** `compute_cdmi(bars)`, adaptive period ถูกต้อง, registered, pytest ผ่าน

---

#### IND-M-38 | Rainbow Oscillator | `rainbow`

| Field | Value |
|-------|-------|
| pandas-ta | custom: SMA ของ SMA ซ้อนกัน 10 ชั้น |
| formula | R1=SMA(Close,2); R2=SMA(R1,2); … R10=SMA(R9,2); Highest/Lowest ของ R1..R10 |
| ref | https://www.investopedia.com/articles/trading/10/rainbow-moving-average.asp |

**Match BUY:** Close > Highest rainbow line (ทะลุขึ้นทุกชั้น)  
**Match SELL:** Close < Lowest rainbow line  
**File:** `api/services/indicators/momentum/rainbow.py`  
**AC:** `compute_rainbow(bars)`, 10-layer smoothing ถูกต้อง, registered, pytest ผ่าน

---

#### IND-M-39 | Schaff Trend Cycle (Momentum Use) | skipped — อยู่ใน trend แล้ว (IND-T-20)

#### IND-M-39 | Pring KST (already IND-M-16) — ใช้ IND-M-39 สำหรับ:

#### IND-M-39 | Gann Swing Oscillator | `gann_swing`

| Field | Value |
|-------|-------|
| pandas-ta | custom |
| formula | นับ N-bar high/low sequence: swing up ถ้า 2 consecutive higher highs; swing down ถ้า 2 consecutive lower lows |
| ref | https://www.investopedia.com/terms/g/gann-angles.asp |

**Match BUY:** Gann swing = up (+1)  
**Match SELL:** Gann swing = down (−1)  
**File:** `api/services/indicators/momentum/gann_swing.py`  
**AC:** `compute_gann_swing(bars)`, swing detection ถูกต้อง, registered, pytest ผ่าน

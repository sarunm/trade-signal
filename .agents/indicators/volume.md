# Volume Indicators — 19 Tasks

**assignee:** codex | **status:** done | **priority:** low | **group:** volume

> **หมายเหตุ:** MT5 ส่ง tick_volume (ไม่ใช่ real volume) ใช้ได้แต่ accuracy ต่ำกว่า stock market

ทุก task block กับ **Indicator Engine Infrastructure**

---

#### IND-V-01 | On-Balance Volume | `obv`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.obv()` → `OBV` |
| formula | OBV = OBV_prev + (Close > Close_prev ? Vol : Close < Close_prev ? −Vol : 0) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:on_balance_volume_obv |

**Match BUY:** OBV trending up (OBV > EMA(OBV, 20))  
**Match SELL:** OBV trending down  
**File:** `api/services/indicators/volume/obv.py`  
**AC:** `compute_obv(bars)`, trend detection via EMA, registered, pytest ผ่าน

---

#### IND-V-02 | VWAP | `vwap`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.vwap()` → `VWAP_D` |
| formula | VWAP = Σ(TP × Vol) / Σ(Vol); TP = (H+L+C)/3; reset ทุก session |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:vwap_intraday |

**Match BUY:** close > VWAP  
**Match SELL:** close < VWAP  
**File:** `api/services/indicators/volume/vwap.py`  
**AC:** `compute_vwap(bars)`, session reset ถูกต้อง (ทุกวัน), registered, pytest ผ่าน

---

#### IND-V-03 | Anchored VWAP | `avwap`

| Field | Value |
|-------|-------|
| pandas-ta | custom: VWAP คำนวณจาก trade entry date ย้อนหลัง N วัน |
| formula | AVWAP = Σ(TP × Vol, since anchor) / Σ(Vol, since anchor) |
| ref | https://www.investopedia.com/terms/a/anchored-vwap.asp |

**Match BUY:** close > AVWAP (ราคาเหนือ VWAP นับจาก swing low สำคัญ)  
**Match SELL:** close < AVWAP  
**File:** `api/services/indicators/volume/avwap.py`  
**AC:** `compute_avwap(bars, anchor_idx)`, registered, pytest ผ่าน

---

#### IND-V-04 | Accumulation/Distribution Line | `ad`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.ad()` → `AD` |
| formula | MFM = ((Close−Low) − (High−Close)) / (High−Low); MFV = MFM × Vol; A/D = Σ(MFV) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:accumulation_distribution_line |

**Match BUY:** A/D trending up (rising)  
**Match SELL:** A/D trending down  
**File:** `api/services/indicators/volume/ad.py`  
**AC:** `compute_ad(bars)`, MFM/MFV calculation ถูกต้อง, registered, pytest ผ่าน

---

#### IND-V-05 | Chaikin Money Flow | `cmf`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.cmf(length=20)` → `CMF_20` |
| formula | CMF = Σ(MFV, N) / Σ(Vol, N); range −1 ถึง +1 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:chaikin_money_flow_cmf |

**Match BUY:** CMF > 0  
**Match SELL:** CMF < 0  
**File:** `api/services/indicators/volume/cmf.py`  
**AC:** `compute_cmf(bars, period=20)`, registered, pytest ผ่าน

---

#### IND-V-06 | Chaikin Oscillator | `chaikin_osc`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.adosc(fast=3, slow=10)` → `ADOSC_3_10` |
| formula | CHAIKIN = EMA3(A/D) − EMA10(A/D) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:chaikin_oscillator |

**Match BUY:** Chaikin Osc > 0  
**Match SELL:** Chaikin Osc < 0  
**File:** `api/services/indicators/volume/chaikin_osc.py`  
**AC:** `compute_chaikin_osc(bars)`, registered, pytest ผ่าน

---

#### IND-V-07 | Money Flow Index | `mfi`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.mfi(length=14)` → `MFI_14` |
| formula | MFR = PosMF / NegMF; MFI = 100 − 100/(1+MFR); TP × Vol = raw money flow |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:money_flow_index_mfi |

**Match BUY:** MFI < 20 (oversold)  
**Match SELL:** MFI > 80 (overbought)  
**File:** `api/services/indicators/volume/mfi.py`  
**AC:** `compute_mfi(bars, period=14)`, OB/OS threshold ถูกต้อง, registered, pytest ผ่าน

---

#### IND-V-08 | Volume Price Trend | `vpt`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.pvt()` → `PVT` |
| formula | VPT = VPT_prev + Vol × (Close − Close_prev) / Close_prev |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:volume_price_trend_vpt |

**Match BUY:** VPT rising (VPT > EMA(VPT, 20))  
**Match SELL:** VPT falling  
**File:** `api/services/indicators/volume/vpt.py`  
**AC:** `compute_vpt(bars)`, trend detection, registered, pytest ผ่าน

---

#### IND-V-09 | Klinger Oscillator | `kvo`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.kvo(fast=34, slow=55, signal=13)` → `KVO_34_55_13`, `KVOs_34_55_13` |
| formula | Volume Force = Vol × 2 × (DM/CM − 1) × TF × 100; KVO = EMA34(VF) − EMA55(VF) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:klinger_oscillator |

**Match BUY:** KVO > Signal  
**Match SELL:** KVO < Signal  
**File:** `api/services/indicators/volume/kvo.py`  
**AC:** `compute_kvo(bars)`, registered, pytest ผ่าน

---

#### IND-V-10 | Ease of Movement | `eom`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.eom(length=14, divisor=100000000)` → `EOM_14_100000000` |
| formula | EMV = ((H+L)/2 − (H_prev+L_prev)/2) / (Vol / (H−L)); EOM = SMA(EMV, N) |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:ease_of_movement_emv |

**Match BUY:** EOM > 0 (ราคาขึ้นง่าย)  
**Match SELL:** EOM < 0  
**File:** `api/services/indicators/volume/eom.py`  
**AC:** `compute_eom(bars)`, registered, pytest ผ่าน

---

#### IND-V-11 | Positive Volume Index | `pvi`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.pvi(signal=255)` → `PVI_1`, `PVIs_255` |
| formula | PVI = PVI_prev + (Close−Close_prev)/Close_prev × PVI_prev เมื่อ Vol > Vol_prev |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:positive_volume_index_pvi |

**Match BUY:** PVI > EMA(PVI, 255)  
**Match SELL:** PVI < EMA(PVI, 255)  
**File:** `api/services/indicators/volume/pvi.py`  
**AC:** `compute_pvi(bars)`, vol condition ถูกต้อง, registered, pytest ผ่าน

---

#### IND-V-12 | Negative Volume Index | `nvi`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.nvi(signal=255)` → `NVI_1`, `NVIs_255` |
| formula | NVI = NVI_prev + (Close−Close_prev)/Close_prev × NVI_prev เมื่อ Vol < Vol_prev |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:negative_volume_index_nvi |

**Match BUY:** NVI > EMA(NVI, 255)  
**Match SELL:** NVI < EMA(NVI, 255)  
**File:** `api/services/indicators/volume/nvi.py`  
**AC:** `compute_nvi(bars)`, registered, pytest ผ่าน

---

#### IND-V-13 | Volume RSI | `vrsi`

| Field | Value |
|-------|-------|
| pandas-ta | custom: RSI ของ volume แทน price |
| formula | VRSI = RSI(Volume, 14) |
| ref | https://www.investopedia.com/terms/v/volume-rsi.asp |

**Match BUY:** VRSI > 50 และ close > close_prev (volume surge ขึ้น)  
**Match SELL:** VRSI > 50 และ close < close_prev  
**File:** `api/services/indicators/volume/vrsi.py`  
**AC:** `compute_vrsi(bars, period=14)`, registered, pytest ผ่าน

---

#### IND-V-14 | Relative Volume | `rvol`

| Field | Value |
|-------|-------|
| pandas-ta | custom: Vol / SMA(Vol, 20) |
| formula | RVOL = Current Volume / Average Volume(N) |
| ref | https://www.investopedia.com/terms/r/relative-volume.asp |

**Match BUY:** RVOL > 1.5 (unusual volume ขึ้น)  
**Match SELL:** RVOL > 1.5 (unusual volume ลง) — ใช้ร่วม direction จาก close  
**File:** `api/services/indicators/volume/rvol.py`  
**AC:** `compute_rvol(bars, period=20)`, registered, pytest ผ่าน

---

#### IND-V-15 | Percentage Volume Oscillator | `pvo`

| Field | Value |
|-------|-------|
| pandas-ta | `df.ta.pvo(fast=12, slow=26, signal=9)` → `PVO_12_26_9`, `PVOh_12_26_9` |
| formula | PVO = (EMA12(Vol) − EMA26(Vol)) / EMA26(Vol) × 100 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:percentage_volume_oscillator_pvo |

**Match BUY:** PVO > 0 (volume กำลัง expanding)  
**Match SELL:** PVO > 0 (expanding volume ลง)  
**File:** `api/services/indicators/volume/pvo.py`  
**AC:** `compute_pvo(bars)`, registered, pytest ผ่าน

---

#### IND-V-16 | Trade Volume Index | `tvi`

| Field | Value |
|-------|-------|
| pandas-ta | custom: classify tick ว่า accumulation หรือ distribution |
| formula | TVI += Vol ถ้า TP > TP_prev; TVI −= Vol ถ้า TP < TP_prev |
| ref | https://www.fmlabs.com/reference/default.htm?url=TVI.htm |

**Match BUY:** TVI rising  
**Match SELL:** TVI falling  
**File:** `api/services/indicators/volume/tvi.py`  
**AC:** `compute_tvi(bars)`, registered, pytest ผ่าน

---

#### IND-V-17 | Volume Profile | `vol_profile`

| Field | Value |
|-------|-------|
| pandas-ta | custom: histogram volume ตาม price level (granularity = ATR/10) |
| formula | POC = price level ที่มี volume สูงสุด; VAH = value area high; VAL = value area low |
| ref | https://www.investopedia.com/terms/v/volume-profile.asp |

**Match BUY:** entry price ≤ VAL (เทรดจาก value area ล่าง)  
**Match SELL:** entry price ≥ VAH  
**File:** `api/services/indicators/volume/vol_profile.py`  
**AC:** `compute_vol_profile(bars)` คืน POC/VAH/VAL, match logic ถูกต้อง, registered, pytest ผ่าน

---

#### IND-V-18 | Smart Money Index | `smi_vol`

| Field | Value |
|-------|-------|
| pandas-ta | custom |
| formula | SMI = close − open ของ 30 min แรกของวัน (retail panic) + close − open ของ 30 min สุดท้าย (smart money) |
| ref | https://www.investopedia.com/terms/s/smart-money-index.asp |

**Match BUY:** SMI rising over past 5 sessions  
**Match SELL:** SMI falling  
**File:** `api/services/indicators/volume/smi_vol.py`  
**AC:** `compute_smi_vol(bars)`, session slicing ถูกต้อง, registered, pytest ผ่าน

---

#### IND-V-19 | Volume (Raw) | `volume_raw`

| Field | Value |
|-------|-------|
| pandas-ta | raw: `bars["tick_volume"]` |
| formula | สังเกต volume spike: Vol > SMA(Vol,20) × 2 |
| ref | https://school.stockcharts.com/doku.php?id=technical_indicators:volume |

**Match BUY:** Vol spike และ close > open (volume surge ขึ้น)  
**Match SELL:** Vol spike และ close < open  
**File:** `api/services/indicators/volume/volume_raw.py`  
**AC:** `compute_volume_raw(bars)`, spike detection, registered, pytest ผ่าน

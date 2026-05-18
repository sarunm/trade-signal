# Trade Signal Partner

ระบบ trading partner ส่วนตัวสำหรับ XAUUSD (Gold) บน MT5 (Mac) — เรียนรู้จากประวัติเทรดจริง วิเคราะห์ pattern สร้าง insight และเปรียบเทียบ paper trade กับ real trade แบบ near-realtime

---

## การเริ่มต้นใช้งาน

```bash
# เปิด full stack
docker compose up --build -d

# ดู logs
docker compose logs -f api

# รัน tests
/Users/nick/.venv/bin/python -m pytest tests/ -v
```

เปิดเบราว์เซอร์ที่ `http://localhost:3000`

---

## EA (TradeSignalBridge)

ตั้งค่าก่อนใช้:
1. MT5 → Tools → Options → Expert Advisors → Allow WebRequest → เพิ่ม `http://127.0.0.1:8000`
2. Attach EA บน chart GOLD
3. ตั้ง `InpSymbol = GOLD` (หรือชื่อ symbol ที่ broker ใช้)
4. ดู Experts tab — ควรเห็น `Health check OK`

---

## Changelog

### Dashboard v1.1 — 2026-05-18
- **Alert panel:** จัดกลุ่ม pattern alert ตาม Timeframe (TF ใหญ่ขึ้นก่อน — H4 → H1)
- **Alert panel:** แสดงเฉพาะ alert ล่าสุด 3 อันต่อ TF
- **Alert panel:** เพิ่มลูกศร ↑ เขียว (bullish) / ↓ แดง (bearish) ในแต่ละ alert
- **Account bar:** เปลี่ยนหน่วยเงินเป็น ฿ (บาท)

### Dashboard v1.0 — Phase 3 — 2026-05-18
React dashboard หน้าเดียว polling ทุก 30 วินาที ประกอบด้วย:
- **Account bar:** แสดง Equity, Balance, Margin, Free Margin, Float P/L พร้อม "Updated Xs ago"
- **Alerts panel:** แสดง alert ที่ยังไม่ acknowledge ก่อน มีปุ่ม Ack กด confirm ได้ทันที
- **Insights panel:** เรียงตาม confidence สูงสุดก่อน แสดง type badge + % + จำนวน sample
- **Open Positions:** จับคู่ real trade กับ paper trade ตาม ticket แสดง entry/SL/TP
- **Closed Trades:** เปรียบเทียบ P/L จริง vs paper พร้อม diff column (เขียว/แดง)
- Backend เพิ่ม `GET /api/account`, `GET /api/trades`, CORS middleware
- เพิ่ม PatternDetector (Pin Bar + Engulfing บน H1/H4) → สร้าง pattern_alert
- เพิ่ม insight ประเภท `pattern_win_rate` — correlate pattern กับผลเทรดจริง
- Docker frontend service พอร์ต 3000

---

### EA v1.03 — 2026-05-18
- เพิ่ม market tick throttle (`InpMarketTickSec`) สำหรับ paper exit
- รองรับ bid/ask post สำหรับ paper trade exit monitoring

### EA v1.02 — 2026-05-18
- **Startup sync:** เปิด EA / เปิด MT5 ใหม่ จะส่ง open positions และ history deals ย้อนหลังอัตโนมัติ
- input ใหม่ `InpSyncDays` (default 30) — ปรับได้ว่าจะดึงประวัติย้อนหลังกี่วัน
- ป้องกันข้อมูลหายเมื่อ EA ถูกปิดกลางคัน (upsert by ticket — ไม่ duplicate)

### EA v1.01 — 2026-05-18
- **Health check ตอน init:** ยิง `GET /health` ทันทีที่ attach EA แจ้งผลใน Experts tab
- **Log symbol ที่ถูกกรองทิ้ง:** ถ้า broker ใช้ชื่ออื่น (เช่น `GOLD`, `XAUUSDm`) จะเห็นใน log ทันที
- **Log HTTP response:** แสดง status code + response body เมื่อ API ตอบ error
- เปลี่ยน default URL เป็น `http://127.0.0.1:8000` (MT5 ไม่รองรับ `localhost`)
- เปลี่ยน default symbol เป็น `GOLD`

### EA v1.00 — Phase 1 — 2026-05-17
EA พื้นฐานสำหรับ bridge ระหว่าง MT5 กับ API:
- ส่ง trade event ทุกครั้งที่มี order/deal (`OnTradeTransaction`)
- ส่ง price tick + account snapshot ทุก 60 วินาที (`OnTimer`) พร้อม OHLCV ทุก timeframe (M5→W1)

---

### Phase 2 — Intelligence Layer — 2026-05-17
- **Insight Engine:** วิเคราะห์ `time_bias` (ชั่วโมงที่แพ้บ่อย) และ `session_bias` (session ที่แพ้บ่อย)
- **Mirror Paper Trader:** เปิด paper trade คู่ขนานทุก real trade อัตโนมัติ คำนวณ SL/TP จากสถิติ
- **Alert Manager:** แจ้งเตือน 3 ประเภท — equity_buffer (equity ต่ำกว่า threshold), double_down (เปิด order เพิ่มขณะขาดทุน), consecutive_loss (แพ้ติดต่อกัน)
- เพิ่ม API `GET /api/insights` และ `GET /api/alerts` (รวม PATCH acknowledge)

### Phase 1 — Data Pipeline — 2026-05-17
รากฐานของระบบ:
- **Docker Compose:** FastAPI + PostgreSQL/TimescaleDB
- **DB Schema:** ตาราง `trades`, `price_bars` (hypertable), `account_snapshots`, `insights`, `alerts`
- **Trade Logger:** upsert trade ด้วย `(ticket, symbol, is_paper)` — ไม่ duplicate
- **Price Handler:** บันทึก OHLCV bars และ account snapshot ทุก tick
- **Alembic migrations:** จัดการ schema อัตโนมัติ

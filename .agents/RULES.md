# Persistent Rules

Rules ที่ได้จาก bugs, reviews, และ retros — agent ต้องอ่านก่อนเริ่ม task ทุกครั้ง

---

## RULE-1 | MT5 ENTRY_OUT deal type เป็น inverse ของ position direction

**Lesson:** ใน MT5, deal ที่ปิด position (DEAL_ENTRY_OUT) จะมี DEAL_TYPE ที่กลับกัน:
- ปิด BUY position → สร้าง DEAL_TYPE_SELL deal
- ปิด SELL position → สร้าง DEAL_TYPE_BUY deal

ถ้าใช้ DEAL_TYPE ของ ENTRY_OUT deal ตรงๆ เพื่อกำหนด direction จะได้ค่าผิดเสมอ
fix: ส่ง `direction: null` ใน ENTRY_OUT payload เพื่อให้ upsert ไม่ overwrite direction ที่ถูกต้องจาก ENTRY_IN deal

**Apply when:** งานใดที่เกี่ยวข้องกับ MT5 deal history, OnTradeTransaction, หรือ upsert ที่ใช้ DEAL_POSITION_ID เป็น canonical ticket

---

## RULE-2 | Upsert by position_id ต้อง preserve fields ที่ตั้งไว้แล้ว

**Lesson:** Pattern `upsert by DEAL_POSITION_ID` ทำให้ ENTRY_IN และ ENTRY_OUT merge กันเป็น row เดียว
ถ้า ENTRY_OUT ส่ง field ที่ ENTRY_IN ตั้งไว้ถูกต้องแล้ว (เช่น direction, open_price, open_time) จะ overwrite ทับค่าที่ถูก
fix ใน backend: upsert logic ต้องเช็ค `if value is not None` ก่อน setattr (ซึ่ง trade_logger.py ทำอยู่แล้ว)
fix ใน EA: field ที่ไม่ควรเปลี่ยนตอน close ให้ส่ง `null` ไม่ใช่ค่าจริง

**Apply when:** เพิ่ม field ใหม่ใน trade event หรือแก้ EA payload ใดๆ ที่ส่งทั้ง ENTRY_IN และ ENTRY_OUT

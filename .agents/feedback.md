# Agent Feedback

Agents เขียนที่นี่เมื่อ:
- เจอ task ที่ขัดแย้งกัน, scope ไม่ชัด, หรือ requirement น่าสงสัย
- มีข้อแนะนำที่ดีกว่า spec ที่กำหนด
- เจอ technical risk หรือ edge case ที่ Claude ควรรู้
- task ทำไม่ได้บางส่วน พร้อมเหตุผล

Claude อ่าน feedback.md ก่อน review ทุกครั้ง

---

## Format

```
### [AGENT] YYYY-MM-DD — <หัวข้อสั้นๆ>

**Type:** question | suggestion | risk | blocker

**Context:** task หรือ commit ที่เกี่ยวข้อง

**Detail:**
อธิบายสิ่งที่เจอ

**Suggestion (ถ้ามี):**
แนะนำว่าควรทำอะไรแทน

**Status:** open | resolved
```

---

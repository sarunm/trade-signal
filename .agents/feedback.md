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

### [Codex] 2026-05-22 — MCP tools reference endpoints not in this branch

**Type:** risk

**Context:** `TASK: Trader Profile MCP — Phase 1 implementation`

**Detail:**
The approved plan asks for 7 MCP tools. Two of those tools call `/api/account-snapshots` and `/api/price-bars`, but those endpoints are not implemented in this branch or listed in the Phase 1 file map. The MCP server intentionally returns the API response text, so these tools will surface 404 JSON until those endpoints exist.

**Suggestion (ถ้ามี):**
Create follow-up tasks for query endpoints if Claude wants all 7 MCP tools to return useful data immediately.

**Status:** resolved — Task #4 "Add missing MCP endpoints (account-snapshots, price-bars)" added to backlog, assignee: codex, priority: low

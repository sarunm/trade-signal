# Trader Profile, Phase 2 Candidates & MCP Query Layer — Design Spec

**Date:** 2026-05-21  
**Status:** Approved

---

## สรุป (TL;DR)

ระบบนี้ทำ 2 สิ่ง:

**1. สะท้อนตัวตนการเทรด** — dashboard แสดง profile อัตโนมัติว่า "คุณมักเล่น setup ไหน bias ไหน" และ Phase 2 Candidates ที่บอกว่าแต่ละ pattern สะสมไปแล้วกี่ trade จากเป้า 15 trade ที่จะกลายเป็น EA rule ใน Phase 2

**2. ให้ Claude เข้าถึง trade data โดยตรง** — ผ่าน MCP Server 7 tools ทำให้ถามใน Claude Code ได้เลยว่า "setup นี้ชนะบ่อยมั้ย" "equity curve ฉันเป็นยังไง" "trade นี้ควรเข้ามั้ย" โดย Claude ดึงข้อมูลจริงจาก DB มาตอบ

**สิ่งที่ต้องสร้าง:**
- `GET /api/trader-profile` — endpoint ใหม่ (ไม่มี migration ใหม่)
- `TraderProfile.jsx` — component ใหม่ใน dashboard
- `api/mcp/server.py` — MCP server ~120 lines
- `.claude/settings.json` — config ให้ Claude Code รู้จัก MCP server

**ไม่ครอบคลุม:** S/R detection, chart pattern detection, Claude autonomous loop (Phase 2 spec แยก)

---

## Goal

ให้ระบบ "สะท้อนตัวตน" การเทรดกลับหาผู้ใช้ในรูปธรรม — แสดง trading pattern ที่กำลังสะสม, Phase 2 candidate rules ที่กำลังสร้าง, และเปิดให้ Claude เข้าถึง trade data โดยตรงเพื่อตอบคำถามและ validate จุดเข้า

---

## Scope (Phase 1 — spec นี้)

1. `GET /api/trader-profile` — aggregate endpoint ใหม่
2. **Trader Profile UI** — section ใหม่ใน dashboard
3. **MCP Server** — 7 tools ให้ Claude query trade data ได้โดยตรง

## Out of Scope (Phase 2 — spec แยก)

- S/R level detection algorithm
- Chart pattern detection (candlestick-based)
- Claude autonomous loop — schedule เช็คตลาดเองแล้ว push suggestion โดยไม่ต้องเปิด dashboard

---

## Architecture

```
Tagged Trades (DB)
       ↓
GET /api/trader-profile   ← endpoint ใหม่ (aggregate query, no new table)
       ↓
TraderProfile component   ← React section ใหม่ใน dashboard

Claude Code session
       ↓
MCP Server (api/mcp/server.py)
       ↓
FastAPI (localhost:8000)  ← reuse existing endpoints + new trader-profile
       ↓
PostgreSQL DB
```

**ไม่มี migration ใหม่** — query จาก `trades` ที่มีอยู่แล้ว

---

## Section 1: Trader Profile API

### Endpoint

```
GET /api/trader-profile
```

### Logic

**Summary** — หา dominant tag แต่ละ dimension โดย count frequency จาก closed trades ที่มี tag:
- `dominant_setup` — setup_pattern ที่ใช้บ่อยที่สุด
- `dominant_bias` — trade_bias ที่ใช้บ่อยที่สุด
- `dominant_entry` — entry_candle ที่ใช้บ่อยที่สุด
- `dominant_fib` — near_fib_level ที่ใช้บ่อยที่สุด
- `rescue_rate` — สัดส่วน is_rescue=True ในทุก trade
- `total_tagged` — จำนวน trade ที่มี setup_pattern ไม่เป็น null

**Candidates** — group by `(setup_pattern, trade_bias)` นับ trade + คำนวณ win rate:
- แสดงทุก combination ที่มีอย่างน้อย 1 trade
- `win_rate` แสดงเฉพาะเมื่อมี >= 3 trades ใน combination นั้น (ไม่งั้น `null`)
- `threshold` = 15 (จำนวน trade ที่ถือว่า candidate พร้อมเป็น EA rule)
- filter by `account_id` (current account เหมือน endpoint อื่นๆ)

### Response Schema

```python
class CandidateRule(BaseModel):
    setup_pattern: str
    trade_bias: Optional[str]
    count: int
    win_rate: Optional[float]   # null ถ้า < 3 trades
    threshold: int = 15

class TraderProfileSummary(BaseModel):
    dominant_setup: Optional[str]
    dominant_bias: Optional[str]
    dominant_entry: Optional[str]
    dominant_fib: Optional[str]
    rescue_rate: float
    total_tagged: int

class TraderProfileResponse(BaseModel):
    summary: TraderProfileSummary
    candidates: List[CandidateRule]
```

---

## Section 2: Trader Profile UI

### Placement

Section ใหม่ใน `App.jsx` — ด้านบนสุด เหนือ Open Trades

### Component: `TraderProfile.jsx`

```
┌─────────────────────────────────────────────┐
│  Trader Profile                             │
│                                             │
│  "คุณมักเล่น แนวรับ + Bullish              │
│   entry Engulfing (M15) near 0.618"         │
│                                             │
│  8 tagged trades · rescue rate 25%          │
├─────────────────────────────────────────────┤
│  Phase 2 Candidates                         │
│                                             │
│  แนวรับ + Bullish    ████░░░░░  5/15  60%  │
│  Double Bottom       ██░░░░░░░  2/15   —   │
│  แนวต้าน + Bearish   █░░░░░░░░  1/15   —   │
└─────────────────────────────────────────────┘
```

**Narrative generation logic:**
- ถ้า `total_tagged < 3` → แสดง "Tag trades เพิ่มเพื่อดู profile ของคุณ"
- ถ้ามีข้อมูล → build sentence จาก dominant fields ที่ไม่เป็น null

**Progress bar:** `count / threshold` คำนวณ % สำหรับความกว้าง

**Win rate display:**
- `—` ถ้า win_rate เป็น null (< 3 trades)
- สี green ถ้า >= 60%, yellow ถ้า 40–59%, red ถ้า < 40%

**Fetch:** `GET /api/trader-profile` ทุก 60 วินาที (เหมือน polling อื่นๆ ใน dashboard)

---

## Section 3: MCP Server

### Files

```
api/mcp/
  __init__.py
  server.py       ← MCP server (~120 lines)

.claude/settings.json   ← เพิ่ม mcpServers block
```

### Configuration

```json
// .claude/settings.json
{
  "mcpServers": {
    "trade-signal": {
      "command": "python",
      "args": ["api/mcp/server.py"],
      "env": {
        "API_BASE": "http://localhost:8000"
      }
    }
  }
}
```

### 7 Tools

| Tool | Method + Path | Parameters | ใช้สำหรับ |
|------|--------------|------------|-----------|
| `get_trades` | `GET /api/trades` | `state` (open/closed), `limit`, `days` | ดู trade ล่าสุด |
| `get_trader_profile` | `GET /api/trader-profile` | — | profile + candidates |
| `get_insights` | `GET /api/insights` | — | insight ที่ engine คำนวณ |
| `get_alerts` | `GET /api/alerts` | — | alert ที่ยัง active |
| `get_account_history` | `GET /api/account-snapshots` | `days` | equity curve, drawdown |
| `get_trade_stats` | `GET /api/insights/summary` | — | win rate, avg profit, risk per trade |
| `get_price_context` | `GET /api/price-bars` | `symbol`, `tf`, `around_time` | market context รอบ entry |

### MCP server pattern (server.py)

```python
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
app = Server("trade-signal")

@app.tool()
async def get_trades(state: str = "closed", limit: int = 50) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{API_BASE}/api/trades", params={"state": state, "limit": limit})
        return r.text

# ... similar pattern for each tool

if __name__ == "__main__":
    import asyncio
    asyncio.run(stdio_server(app))
```

### ใช้งาน

เปิด Claude Code ใน project directory — tools ถูก load อัตโนมัติ สามารถถามได้เลย:

> "ช่วง 2 สัปดาห์ที่ผ่านมา setup ไหนชนะบ่อยที่สุด?"  
> "ผมกำลังจะเข้า แนวรับ + Bullish ตอนนี้ — ตรงกับ pattern ที่ผมชนะมั้ย?"  
> "rescue trade ของผมได้ผลมั้ย?"

---

## Testing

- `GET /api/trader-profile` returns correct dominant tags from seeded trades
- Candidate win_rate เป็น null เมื่อ trade < 3, แสดงค่าเมื่อ >= 3
- TraderProfile component แสดง "Tag trades เพิ่ม..." เมื่อ total_tagged < 3
- MCP `get_trades` tool returns JSON string from API
- MCP tools handle API down gracefully (return error message string)

---

## Future: Phase 2 (Autonomous Loop + Mobile)

*out of scope สำหรับ spec นี้ — บันทึกไว้เป็น reference*

### Analysis Upgrades
- **S/R Detection** — คำนวณแนวรับ/แนวต้านจาก price_bars (pivot points, price clusters)
- **Chart Pattern Detection** — ตรวจ double top/bottom, rounded top/bottom จาก candlestick shape

### Claude → Mobile (Push)
- **Claude Cron Loop** — Claude CLI รัน schedule บน Mac (เช่น ทุก 30 นาที) เช็ค trade data ผ่าน MCP แล้ว push notification ไปหาผู้ใช้
- **LINE Notify / LINE Messaging API** — Claude POST ผลวิเคราะห์ไปที่ LINE ของผู้ใช้โดยตรง ไม่ต้องเปิด dashboard

### Mobile → Claude (Two-way)
- **LINE Bot + Webhook** — ผู้ใช้ส่งข้อความใน LINE เช่น "วิเคราะห์ trade ผม" → webhook บน Mac รับ → เรียก Claude API พร้อม trade context → ตอบกลับใน LINE
- **Infrastructure**: LINE Messaging API + ngrok (dev) หรือ VPS เล็กๆ (prod) รับ webhook

### Memory-driven Learning
- Claude วิเคราะห์ trade ใหม่ → เปรียบเทียบกับ memory ที่สะสม → แนะนำเฉพาะตัวขึ้นเรื่อยๆ
- memory file สะสม insight เช่น "user ชนะเมื่อ fib distance < 3 pts, rescue trade ได้ผลแค่ 30%"

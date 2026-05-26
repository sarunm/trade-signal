# Trader Profile, Phase 2 Candidates & MCP Query Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a Trader Profile section to the dashboard showing dominant trading patterns + Phase 2 candidate rules, and expose trade data via MCP so Claude can answer trading questions directly.

**Architecture:** New `GET /api/trader-profile` endpoint aggregates tagged trades into summary + candidate rules. New `TraderProfile.jsx` component renders this in the dashboard. MCP server at `api/mcp/server.py` wraps 7 existing API endpoints as Claude-queryable tools.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async, React + Tailwind, MCP Python SDK (`mcp[cli]`), httpx

**Spec:** `docs/superpowers/specs/2026-05-21-trader-profile-mcp-design.md`

---

## File Map

| Action | File |
|--------|------|
| Create | `api/schemas/trader_profile.py` |
| Create | `api/routers/trader_profile.py` |
| Modify | `api/main.py` |
| Create | `tests/test_trader_profile.py` |
| Create | `frontend/src/components/TraderProfile.jsx` |
| Modify | `frontend/src/App.jsx` |
| Create | `api/mcp/__init__.py` |
| Create | `api/mcp/server.py` |
| Modify | `api/requirements.txt` |
| Modify | `.claude/settings.local.json` |

---

## Task 1: Trader Profile Schema

**Files:**
- Create: `api/schemas/trader_profile.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_trader_profile.py
import pytest
from schemas.trader_profile import CandidateRule, TraderProfileSummary, TraderProfileResponse

def test_candidate_rule_win_rate_optional():
    c = CandidateRule(setup_pattern="support", trade_bias="bullish", count=2, win_rate=None, threshold=15)
    assert c.win_rate is None
    assert c.threshold == 15

def test_trader_profile_response_structure():
    summary = TraderProfileSummary(
        dominant_setup="support",
        dominant_bias="bullish",
        dominant_entry=None,
        dominant_fib=None,
        rescue_rate=0.25,
        total_tagged=8,
    )
    profile = TraderProfileResponse(summary=summary, candidates=[])
    assert profile.summary.total_tagged == 8
    assert profile.candidates == []
```

- [x] **Step 2: Run test to verify it fails**

```bash
docker compose exec api python -m pytest ../tests/test_trader_profile.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'schemas.trader_profile'`

- [x] **Step 3: Create schema file**

```python
# api/schemas/trader_profile.py
from typing import List, Optional
from pydantic import BaseModel


class CandidateRule(BaseModel):
    setup_pattern: str
    trade_bias: Optional[str] = None
    count: int
    win_rate: Optional[float] = None   # null if < 3 trades in combination
    threshold: int = 15


class TraderProfileSummary(BaseModel):
    dominant_setup: Optional[str] = None
    dominant_bias: Optional[str] = None
    dominant_entry: Optional[str] = None
    dominant_fib: Optional[str] = None
    rescue_rate: float
    total_tagged: int


class TraderProfileResponse(BaseModel):
    summary: TraderProfileSummary
    candidates: List[CandidateRule]
```

- [x] **Step 4: Run test to verify it passes**

```bash
docker compose exec api python -m pytest ../tests/test_trader_profile.py -v
```

Expected: PASS (2 tests)

- [x] **Step 5: Commit**

```bash
git add api/schemas/trader_profile.py tests/test_trader_profile.py
git commit -m "feat: add TraderProfile pydantic schemas"
```

---

## Task 2: Trader Profile API Endpoint

**Files:**
- Create: `api/routers/trader_profile.py`
- Modify: `api/main.py`

- [x] **Step 1: Write failing tests**

Add to `tests/test_trader_profile.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from main import app

@pytest.mark.asyncio
async def test_trader_profile_empty():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/trader-profile")
    assert r.status_code == 200
    data = r.json()
    assert data["summary"]["total_tagged"] == 0
    assert data["summary"]["rescue_rate"] == 0.0
    assert data["candidates"] == []

@pytest.mark.asyncio
async def test_trader_profile_win_rate_hidden_below_3(seed_tagged_trades):
    # seed_tagged_trades fixture inserts 2 trades: support+bullish, 1 win
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/trader-profile")
    data = r.json()
    candidate = next(c for c in data["candidates"] if c["setup_pattern"] == "support")
    assert candidate["count"] == 2
    assert candidate["win_rate"] is None   # hidden: < 3 trades

@pytest.mark.asyncio
async def test_trader_profile_win_rate_shown_at_3(seed_tagged_trades_3):
    # seed_tagged_trades_3 inserts 3 trades: support+bullish, 2 wins
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/trader-profile")
    data = r.json()
    candidate = next(c for c in data["candidates"] if c["setup_pattern"] == "support")
    assert candidate["count"] == 3
    assert candidate["win_rate"] == pytest.approx(2/3, abs=0.01)
```

- [x] **Step 2: Add fixtures to `tests/conftest.py`**

Open `tests/conftest.py` and add these fixtures after existing ones:

```python
import datetime as dt
from decimal import Decimal
from models.trade import Trade, Direction, OrderState

@pytest.fixture
async def seed_tagged_trades(session):
    trades = [
        Trade(
            ticket=9001, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_price=Decimal("3280.00"), close_price=Decimal("3290.00"),
            profit=Decimal("10.00"), setup_pattern="support", trade_bias="bullish",
            open_time=dt.datetime.now(dt.timezone.utc),
        ),
        Trade(
            ticket=9002, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_price=Decimal("3285.00"), close_price=Decimal("3278.00"),
            profit=Decimal("-7.00"), setup_pattern="support", trade_bias="bullish",
            open_time=dt.datetime.now(dt.timezone.utc),
        ),
    ]
    session.add_all(trades)
    await session.commit()
    yield trades
    for t in trades:
        await session.delete(t)
    await session.commit()

@pytest.fixture
async def seed_tagged_trades_3(session):
    trades = [
        Trade(
            ticket=9003, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_price=Decimal("3280.00"), close_price=Decimal("3290.00"),
            profit=Decimal("10.00"), setup_pattern="support", trade_bias="bullish",
            open_time=dt.datetime.now(dt.timezone.utc),
        ),
        Trade(
            ticket=9004, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_price=Decimal("3285.00"), close_price=Decimal("3295.00"),
            profit=Decimal("10.00"), setup_pattern="support", trade_bias="bullish",
            open_time=dt.datetime.now(dt.timezone.utc),
        ),
        Trade(
            ticket=9005, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_price=Decimal("3290.00"), close_price=Decimal("3283.00"),
            profit=Decimal("-7.00"), setup_pattern="support", trade_bias="bullish",
            open_time=dt.datetime.now(dt.timezone.utc),
        ),
    ]
    session.add_all(trades)
    await session.commit()
    yield trades
    for t in trades:
        await session.delete(t)
    await session.commit()
```

- [x] **Step 3: Run tests to verify they fail**

```bash
docker compose exec api python -m pytest ../tests/test_trader_profile.py -v
```

Expected: FAIL with `404` or import error (router not registered yet)

- [x] **Step 4: Create the router**

```python
# api/routers/trader_profile.py
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, case, select

from database import get_session
from models.account_snapshot import AccountSnapshot
from models.trade import Trade
from schemas.trader_profile import CandidateRule, TraderProfileResponse, TraderProfileSummary

router = APIRouter(prefix="/api", tags=["trader-profile"])

WIN_RATE_MIN_TRADES = 3
CANDIDATE_THRESHOLD = 15


async def _current_account_id(session: AsyncSession) -> Optional[int]:
    result = await session.execute(
        select(AccountSnapshot.account_id)
        .where(AccountSnapshot.account_id.isnot(None))
        .order_by(AccountSnapshot.timestamp.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _account_filter(account_id: Optional[int]):
    if account_id is not None:
        return Trade.account_id == account_id
    return True


@router.get("/trader-profile", response_model=TraderProfileResponse)
async def get_trader_profile(session: AsyncSession = Depends(get_session)):
    account_id = await _current_account_id(session)
    acc_filter = _account_filter(account_id)

    closed_filter = (Trade.close_price.isnot(None), acc_filter)

    # dominant tags — most frequent per dimension across closed tagged trades
    async def dominant(column):
        r = await session.execute(
            select(column, func.count().label("cnt"))
            .where(*closed_filter, column.isnot(None))
            .group_by(column)
            .order_by(func.count().desc())
            .limit(1)
        )
        row = r.first()
        return row[0] if row else None

    dominant_setup = await dominant(Trade.setup_pattern)
    dominant_bias = await dominant(Trade.trade_bias)
    dominant_entry = await dominant(Trade.entry_candle)
    dominant_fib = await dominant(Trade.near_fib_level)

    # rescue rate + total tagged
    totals = await session.execute(
        select(
            func.count().label("total"),
            func.sum(case((Trade.is_rescue == True, 1), else_=0)).label("rescue_count"),
            func.sum(case((Trade.setup_pattern.isnot(None), 1), else_=0)).label("tagged_count"),
        )
        .where(acc_filter)
    )
    row = totals.first()
    total = row.total or 0
    rescue_rate = float(row.rescue_count or 0) / max(total, 1)
    total_tagged = int(row.tagged_count or 0)

    # candidates — group by (setup_pattern, trade_bias)
    cand_rows = await session.execute(
        select(
            Trade.setup_pattern,
            Trade.trade_bias,
            func.count().label("cnt"),
            func.sum(case((Trade.profit > 0, 1), else_=0)).label("wins"),
        )
        .where(*closed_filter, Trade.setup_pattern.isnot(None))
        .group_by(Trade.setup_pattern, Trade.trade_bias)
        .order_by(func.count().desc())
    )
    candidates = []
    for r in cand_rows.all():
        cnt = r.cnt
        win_rate = float(r.wins) / cnt if cnt >= WIN_RATE_MIN_TRADES else None
        candidates.append(
            CandidateRule(
                setup_pattern=r.setup_pattern,
                trade_bias=r.trade_bias,
                count=cnt,
                win_rate=win_rate,
                threshold=CANDIDATE_THRESHOLD,
            )
        )

    return TraderProfileResponse(
        summary=TraderProfileSummary(
            dominant_setup=dominant_setup,
            dominant_bias=dominant_bias,
            dominant_entry=dominant_entry,
            dominant_fib=dominant_fib,
            rescue_rate=rescue_rate,
            total_tagged=total_tagged,
        ),
        candidates=candidates,
    )
```

- [x] **Step 5: Register router in main.py**

Add after the last import:
```python
from routers.trader_profile import router as trader_profile_router
```

Add after the last `app.include_router(...)`:
```python
app.include_router(trader_profile_router)
```

- [x] **Step 6: Restart API and run tests**

```bash
docker compose restart api
docker compose exec api python -m pytest ../tests/test_trader_profile.py -v
```

Expected: PASS (all 4 tests)

- [x] **Step 7: Smoke test**

```bash
curl -s http://localhost:8000/api/trader-profile | python3 -m json.tool
```

Expected: JSON with `summary` and `candidates` keys

- [x] **Step 8: Commit**

```bash
git add api/routers/trader_profile.py api/main.py tests/test_trader_profile.py tests/conftest.py
git commit -m "feat: add GET /api/trader-profile endpoint"
```

---

## Task 3: TraderProfile React Component

**Files:**
- Create: `frontend/src/components/TraderProfile.jsx`
- Modify: `frontend/src/App.jsx`

- [x] **Step 1: Create TraderProfile.jsx**

```jsx
// frontend/src/components/TraderProfile.jsx
const SETUP_LABELS = {
  support: 'แนวรับ',
  resistance: 'แนวต้าน',
  double_bottom: 'Double Bottom',
  double_top: 'Double Top',
  triple_bottom: 'Triple Bottom',
  triple_top: 'Triple Top',
  rounded_bottom: 'Rounded Bottom',
  rounded_top: 'Rounded Top',
  price_cluster: 'Price Cluster',
  other: 'Other',
}

function buildNarrative(summary) {
  const { dominant_setup, dominant_bias, dominant_entry, dominant_fib, total_tagged } = summary
  if (total_tagged < 3) return null
  const parts = []
  if (dominant_setup) parts.push(SETUP_LABELS[dominant_setup] || dominant_setup)
  if (dominant_bias) parts.push(dominant_bias === 'bullish' ? 'Bullish' : 'Bearish')
  if (dominant_entry) parts.push(`entry ${dominant_entry}`)
  if (dominant_fib) parts.push(`near ${dominant_fib}`)
  if (parts.length === 0) return null
  return `คุณมักเล่น ${parts.join(' + ')}`
}

function winRateColor(rate) {
  if (rate === null) return 'text-gray-500'
  if (rate >= 0.6) return 'text-green-400'
  if (rate >= 0.4) return 'text-yellow-400'
  return 'text-red-400'
}

function CandidateRow({ candidate }) {
  const pct = Math.min((candidate.count / candidate.threshold) * 100, 100)
  const wr = candidate.win_rate !== null ? `${Math.round(candidate.win_rate * 100)}%` : '—'
  const label = [
    SETUP_LABELS[candidate.setup_pattern] || candidate.setup_pattern,
    candidate.trade_bias ? (candidate.trade_bias === 'bullish' ? 'Bullish' : 'Bearish') : null,
  ].filter(Boolean).join(' + ')

  return (
    <div className="flex items-center gap-2 py-1">
      <span className="text-xs text-gray-300 w-40 truncate">{label}</span>
      <div className="flex-1 bg-gray-700 rounded-full h-1.5">
        <div className="bg-blue-500 h-1.5 rounded-full" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400 w-10 text-right">{candidate.count}/{candidate.threshold}</span>
      <span className={`text-xs w-8 text-right ${winRateColor(candidate.win_rate)}`}>{wr}</span>
    </div>
  )
}

export default function TraderProfile({ data, error }) {
  if (error) return null
  if (!data) return null

  const { summary, candidates } = data
  const narrative = buildNarrative(summary)

  return (
    <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
      <h2 className="text-sm font-semibold text-gray-400 mb-3">Trader Profile</h2>
      <div className="mb-3">
        {narrative ? (
          <>
            <p className="text-sm text-gray-100">"{narrative}"</p>
            <p className="text-xs text-gray-500 mt-1">
              {summary.total_tagged} tagged trades
              {summary.rescue_rate > 0 && ` · rescue rate ${Math.round(summary.rescue_rate * 100)}%`}
            </p>
          </>
        ) : (
          <p className="text-xs text-gray-500">Tag trades เพิ่มเพื่อดู profile ของคุณ (ต้องการอย่างน้อย 3 trades)</p>
        )}
      </div>

      {candidates.length > 0 && (
        <>
          <div className="border-t border-gray-800 pt-3">
            <p className="text-xs text-gray-500 mb-2">Phase 2 Candidates</p>
            {candidates.map((c, i) => (
              <CandidateRow key={i} candidate={c} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
```

- [x] **Step 2: Add TraderProfile to App.jsx**

In `frontend/src/App.jsx`:

Add import after other imports:
```jsx
import TraderProfile from './components/TraderProfile'
```

Add fetch + polling after `const fetchFib = ...`:
```jsx
const fetchTraderProfile = useCallback(() => get('/api/trader-profile'), [])
const traderProfile = usePolling(fetchTraderProfile)
```

Add component in the JSX, immediately after `<AccountBar .../>` and before `<DailyPLPanel .../>`:
```jsx
<TraderProfile data={traderProfile.data} error={traderProfile.error} />
```

- [x] **Step 3: Verify in browser**

```bash
# API must be running
open http://localhost:3000
```

Check:
- TraderProfile section appears at top of dashboard (below AccountBar)
- If no tagged trades: shows "Tag trades เพิ่มเพื่อดู profile..."
- If tagged trades exist: shows narrative + candidate rows with progress bars

- [x] **Step 4: Commit**

```bash
git add frontend/src/components/TraderProfile.jsx frontend/src/App.jsx
git commit -m "feat: add TraderProfile component to dashboard"
```

---

## Task 4: MCP Server

**Files:**
- Create: `api/mcp/__init__.py`
- Create: `api/mcp/server.py`
- Modify: `api/requirements.txt`
- Modify: `.claude/settings.local.json`

- [x] **Step 1: Add dependencies to requirements.txt**

In `api/requirements.txt`, add after the last line:
```
mcp[cli]==1.9.0
httpx==0.27.2
```

- [x] **Step 2: Install in container**

```bash
docker compose exec api pip install "mcp[cli]==1.9.0" "httpx==0.27.2"
```

Verify:
```bash
docker compose exec api python -c "from mcp.server.fastmcp import FastMCP; print('ok')"
```

Expected: `ok`

- [x] **Step 3: Create MCP package**

```python
# api/mcp/__init__.py
```

(empty file — marks directory as Python package)

- [x] **Step 4: Create server.py**

```python
# api/mcp/server.py
import asyncio
import os
import httpx
from mcp.server.fastmcp import FastMCP

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
mcp = FastMCP("trade-signal")


async def _get(path: str, params: dict = None) -> str:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{API_BASE}{path}", params=params or {})
            return r.text
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def get_trades(state: str = "closed", limit: int = 50) -> str:
    """Get trades. state='open' or 'closed'. limit max 200."""
    return await _get("/api/trades", {"state": state, "limit": limit})


@mcp.tool()
async def get_trader_profile() -> str:
    """Get trader profile: dominant trading style and Phase 2 candidate rules with progress."""
    return await _get("/api/trader-profile")


@mcp.tool()
async def get_insights() -> str:
    """Get active insights computed by the insight engine (win rates, patterns, etc)."""
    return await _get("/api/insights")


@mcp.tool()
async def get_alerts() -> str:
    """Get currently active (unacknowledged) alerts."""
    return await _get("/api/alerts")


@mcp.tool()
async def get_account_history(days: int = 7) -> str:
    """Get account equity/balance snapshots for the last N days. Use for equity curve and drawdown analysis."""
    return await _get("/api/account-snapshots", {"days": days})


@mcp.tool()
async def get_trade_stats() -> str:
    """Get aggregated trade statistics: win rate, average profit, daily P&L."""
    return await _get("/api/daily-pl", {"days": 30})


@mcp.tool()
async def get_price_context(symbol: str = "XAUUSD", tf: str = "M15", limit: int = 50) -> str:
    """Get recent price bars for a symbol and timeframe. Use to understand market context around entries.
    tf options: M5, M15, M30, H1, H4, D, W1"""
    return await _get("/api/price-bars", {"symbol": symbol, "tf": tf, "limit": limit})


if __name__ == "__main__":
    mcp.run()
```

- [x] **Step 5: Test server starts**

```bash
cd /Users/nick/2_SideProjects/trade-signal
/Users/nick/.venv/bin/python api/mcp/server.py &
sleep 2
kill %1
```

Expected: starts without errors (prints MCP startup info)

- [x] **Step 6: Add mcpServers to .claude/settings.local.json**

Open `.claude/settings.local.json` and add `mcpServers` key at the top level alongside `permissions`:

```json
{
  "mcpServers": {
    "trade-signal": {
      "command": "/Users/nick/.venv/bin/python",
      "args": ["api/mcp/server.py"],
      "env": {
        "API_BASE": "http://localhost:8000"
      }
    }
  },
  "permissions": {
    "allow": [
      ...existing entries...
    ]
  }
}
```

- [x] **Step 7: Verify MCP tools load in Claude Code**

Restart Claude Code in the project directory. Run:
```
/mcp
```

Expected: `trade-signal` server listed with 7 tools: `get_trades`, `get_trader_profile`, `get_insights`, `get_alerts`, `get_account_history`, `get_trade_stats`, `get_price_context`

- [x] **Step 8: Test a tool**

In Claude Code, ask:
> "ใช้ get_trader_profile tool แล้วบอกผมว่ามีอะไรบ้าง"

Expected: Claude calls the tool and returns actual data from the API

- [x] **Step 9: Commit**

```bash
git add api/mcp/__init__.py api/mcp/server.py api/requirements.txt .claude/settings.local.json
git commit -m "feat: add MCP server with 7 trade data tools"
```

---

## Done

หลังจาก Task 4 เสร็จ ระบบจะมี:

1. `GET /api/trader-profile` — endpoint aggregate ที่ query จาก tagged trades
2. Trader Profile section ใน dashboard — แสดง narrative + Phase 2 candidates ทันทีที่มี tag
3. MCP server — Claude Code สามารถถามเรื่อง trade data ได้โดยตรงในทุก session

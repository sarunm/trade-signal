# Phase 3: React Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build a single-page React dashboard showing account info, alerts, insights, and paper vs real trade comparisons in near-realtime (30s polling), backed by two new API endpoints, a PatternDetector service, and a `pattern_win_rate` insight type.

**Architecture:** FastAPI backend gains CORS, two new read endpoints (`/api/account`, `/api/trades`), a `PatternDetector` service (pin bar/engulfing on H1/H4 → Alert), and `pattern_win_rate` computation in the insight engine. The React frontend (Vite + TailwindCSS) polls all endpoints every 30s using a shared `usePolling` hook and renders five sections on one page. Docker Compose gains a `frontend` service.

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy 2.0 async (backend), React 18 + Vite 5 + TailwindCSS 3 (frontend), SQLite/aiosqlite (tests), PostgreSQL/TimescaleDB (production), Docker Compose.

**Test runner:** From project root — `/Users/nick/.venv/bin/python -m pytest tests/<file>.py -v`
**All tests:** `/Users/nick/.venv/bin/python -m pytest tests/ -v`

---

## File Map

**Create (backend):**
- `api/schemas/account.py` — AccountResponse Pydantic schema
- `api/schemas/trade.py` — TradeResponse Pydantic schema
- `api/routers/account.py` — GET /api/account
- `api/routers/trades.py` — GET /api/trades
- `api/services/pattern_detector.py` — pure detection functions + DB integration
- `tests/test_account_api.py`
- `tests/test_trades_api.py`
- `tests/test_pattern_detector.py`
- `tests/test_pattern_wire_up.py`

**Modify (backend):**
- `api/main.py` — add CORSMiddleware, include account_router and trades_router
- `api/routers/price_tick.py` — call `run_pattern_detector` after `check_equity_buffer`
- `api/services/insight_engine.py` — add `_compute_pattern_win_rate`

**Create (frontend):**
- `frontend/package.json`
- `frontend/vite.config.js`
- `frontend/tailwind.config.js`
- `frontend/postcss.config.js`
- `frontend/index.html`
- `frontend/src/main.jsx`
- `frontend/src/index.css`
- `frontend/src/App.jsx`
- `frontend/src/hooks/usePolling.js`
- `frontend/src/components/AccountBar.jsx`
- `frontend/src/components/AlertsPanel.jsx`
- `frontend/src/components/InsightsPanel.jsx`
- `frontend/src/components/OpenPositions.jsx`
- `frontend/src/components/ClosedTrades.jsx`
- `frontend/Dockerfile`

**Modify (infra):**
- `docker-compose.yml` — add frontend service

---

## Task 1: CORS + GET /api/account

**Files:**
- Create: `api/schemas/account.py`
- Create: `api/routers/account.py`
- Modify: `api/main.py`
- Create: `tests/test_account_api.py`

- [x] **Step 1: Write the failing tests**

`tests/test_account_api.py`:
```python
import pytest
from decimal import Decimal
from datetime import datetime, timezone
from models.account_snapshot import AccountSnapshot


@pytest.mark.asyncio
async def test_get_account_empty(client):
    response = await client.get("/api/account")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_account_returns_latest(client, db_session):
    t1 = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 5, 18, 10, 1, tzinfo=timezone.utc)
    for t, eq in [(t1, Decimal("1000.00")), (t2, Decimal("2000.00"))]:
        db_session.add(AccountSnapshot(
            timestamp=t,
            equity=eq,
            balance=Decimal("900.00"),
            margin=Decimal("50.00"),
            free_margin=Decimal("950.00"),
            floating_pl=eq - Decimal("900.00"),
        ))
    await db_session.commit()

    response = await client.get("/api/account")
    assert response.status_code == 200
    data = response.json()
    assert float(data["equity"]) == 2000.00
    assert "timestamp" in data
```

- [x] **Step 2: Run to confirm FAIL**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_account_api.py -v
```
Expected: `FAILED` — `404 != 200` or route not found.

- [x] **Step 3: Create `api/schemas/account.py`**

```python
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class AccountResponse(BaseModel):
    equity: Decimal
    balance: Decimal
    margin: Decimal
    free_margin: Decimal
    floating_pl: Decimal
    timestamp: datetime

    model_config = {"from_attributes": True}
```

- [x] **Step 4: Create `api/routers/account.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session
from models.account_snapshot import AccountSnapshot
from schemas.account import AccountResponse

router = APIRouter(prefix="/api", tags=["account"])


@router.get("/account", response_model=AccountResponse)
async def get_account(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(AccountSnapshot).order_by(AccountSnapshot.timestamp.desc()).limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No account snapshot available")
    return snapshot
```

- [x] **Step 5: Update `api/main.py`** — add CORS and include the new router

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine
import models  # noqa: F401
from routers.trade_events import router as trade_events_router
from routers.price_tick import router as price_tick_router
from routers.insights import router as insights_router
from routers.alerts import router as alerts_router
from routers.account import router as account_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Trade Signal Partner", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trade_events_router)
app.include_router(price_tick_router)
app.include_router(insights_router)
app.include_router(alerts_router)
app.include_router(account_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [x] **Step 6: Run tests — expect PASS**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_account_api.py -v
```
Expected: `2 passed`

- [x] **Step 7: Run full suite to check for regressions**

```bash
/Users/nick/.venv/bin/python -m pytest tests/ -v
```
Expected: all existing tests still pass.

- [x] **Step 8: Commit**

```bash
git add api/schemas/account.py api/routers/account.py api/main.py tests/test_account_api.py
git commit -m "feat: add CORS and GET /api/account endpoint"
```

---

## Task 2: GET /api/trades

**Files:**
- Create: `api/schemas/trade.py`
- Create: `api/routers/trades.py`
- Modify: `api/main.py`
- Create: `tests/test_trades_api.py`

- [x] **Step 1: Write the failing tests**

`tests/test_trades_api.py`:
```python
import pytest
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from models.trade import Trade, Direction, OrderState, OrderType


def make_trade(ticket, is_paper=False, close_price=None, profit=None):
    return Trade(
        id=uuid.uuid4(),
        ticket=ticket,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_type=OrderType.market,
        order_state=OrderState.filled,
        open_price=Decimal("1920.00000"),
        close_price=close_price,
        profit=profit,
        volume=Decimal("0.10"),
        is_paper=is_paper,
        open_time=datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
        close_time=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc) if close_price else None,
    )


@pytest.mark.asyncio
async def test_list_open_trades(client, db_session):
    db_session.add(make_trade(1001))
    db_session.add(make_trade(1002, close_price=Decimal("1930.00000"), profit=Decimal("100.00")))
    await db_session.commit()

    response = await client.get("/api/trades?state=open")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticket"] == 1001
    assert data[0]["close_price"] is None


@pytest.mark.asyncio
async def test_list_closed_trades(client, db_session):
    db_session.add(make_trade(1001))
    db_session.add(make_trade(1002, close_price=Decimal("1930.00000"), profit=Decimal("100.00")))
    await db_session.commit()

    response = await client.get("/api/trades?state=closed")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticket"] == 1002


@pytest.mark.asyncio
async def test_list_trades_returns_both_real_and_paper(client, db_session):
    db_session.add(make_trade(1001, is_paper=False))
    db_session.add(make_trade(1001, is_paper=True))
    await db_session.commit()

    response = await client.get("/api/trades?state=open")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_list_closed_trades_limit(client, db_session):
    for i in range(5):
        db_session.add(make_trade(2000 + i, close_price=Decimal("1930.00000"), profit=Decimal("10.00")))
    await db_session.commit()

    response = await client.get("/api/trades?state=closed&limit=3")
    assert response.status_code == 200
    assert len(response.json()) == 3


@pytest.mark.asyncio
async def test_invalid_state_returns_422(client):
    response = await client.get("/api/trades?state=invalid")
    assert response.status_code == 422
```

- [x] **Step 2: Run to confirm FAIL**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_trades_api.py -v
```
Expected: `FAILED` — route not found.

- [x] **Step 3: Create `api/schemas/trade.py`**

```python
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class TradeResponse(BaseModel):
    id: UUID
    ticket: int
    symbol: str
    direction: Optional[str] = None
    order_type: Optional[str] = None
    order_state: Optional[str] = None
    is_paper: bool
    paper_mode: Optional[str] = None
    open_price: Optional[Decimal] = None
    close_price: Optional[Decimal] = None
    tp: Optional[Decimal] = None
    sl: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    profit: Optional[Decimal] = None
    open_time: Optional[datetime] = None
    close_time: Optional[datetime] = None

    model_config = {"from_attributes": True}
```

- [x] **Step 4: Create `api/routers/trades.py`**

```python
from typing import List, Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session
from models.trade import Trade
from schemas.trade import TradeResponse

router = APIRouter(prefix="/api", tags=["trades"])


@router.get("/trades", response_model=List[TradeResponse])
async def list_trades(
    state: Literal["open", "closed"] = Query("open"),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    query = select(Trade).order_by(Trade.open_time.desc())
    if state == "open":
        query = query.where(Trade.close_price.is_(None))
    else:
        query = query.where(Trade.close_price.isnot(None)).limit(limit)
    result = await session.execute(query)
    return result.scalars().all()
```

- [x] **Step 5: Add trades router to `api/main.py`**

Add to imports:
```python
from routers.trades import router as trades_router
```

Add after the existing `app.include_router(account_router)` line:
```python
app.include_router(trades_router)
```

- [x] **Step 6: Run tests — expect PASS**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_trades_api.py -v
```
Expected: `5 passed`

- [x] **Step 7: Run full suite**

```bash
/Users/nick/.venv/bin/python -m pytest tests/ -v
```
Expected: all pass.

- [x] **Step 8: Commit**

```bash
git add api/schemas/trade.py api/routers/trades.py api/main.py tests/test_trades_api.py
git commit -m "feat: add GET /api/trades endpoint"
```

---

## Task 3: PatternDetector Service

Pattern detection logic lives in `api/services/pattern_detector.py`. Pure detection functions (`detect_pin_bar`, `detect_engulfing`) take a list of bar dicts — no DB access, fully testable. `run_pattern_detector` does the DB queries and alert creation.

**Files:**
- Create: `api/services/pattern_detector.py`
- Create: `tests/test_pattern_detector.py`

- [x] **Step 1: Write the failing tests**

`tests/test_pattern_detector.py`:
```python
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import select

from models.price_bar import PriceBar, Timeframe
from models.alert import Alert
from services.pattern_detector import detect_pin_bar, detect_engulfing, run_pattern_detector
from schemas.price_tick import PriceTickSchema, AccountStateSchema


def make_tick(symbol="XAUUSD"):
    return PriceTickSchema(
        timestamp=datetime.now(timezone.utc),
        symbol=symbol,
        account=AccountStateSchema(
            equity=Decimal("10000"), balance=Decimal("10000"),
            margin=Decimal("0"), free_margin=Decimal("10000"),
            floating_pl=Decimal("0"),
        ),
        bars={},
    )


# --- Pure function tests (no DB) ---

def test_detect_pin_bar_bullish():
    # lower_wick=5.0, body=0.5, range=6.0 → 5.0>=1.0 ✓, 5.0>=3.6 ✓
    bars = [{"open": Decimal("1920.0"), "high": Decimal("1921.0"),
             "low": Decimal("1915.0"), "close": Decimal("1920.5")}]
    assert detect_pin_bar(bars) == "bullish"


def test_detect_pin_bar_bearish():
    # upper_wick=5.5, body=0.5, range=6.5 → 5.5>=1.0 ✓, 5.5>=3.9 ✓
    bars = [{"open": Decimal("1920.0"), "high": Decimal("1926.0"),
             "low": Decimal("1919.5"), "close": Decimal("1920.5")}]
    assert detect_pin_bar(bars) == "bearish"


def test_detect_pin_bar_none_for_normal_candle():
    # body=1.0, range=4.0, wicks both small
    bars = [{"open": Decimal("1920.0"), "high": Decimal("1922.0"),
             "low": Decimal("1918.0"), "close": Decimal("1921.0")}]
    assert detect_pin_bar(bars) is None


def test_detect_engulfing_bullish():
    # prev bearish (1921→1919), curr bullish engulfs: open<1919, close>1921
    bars = [
        {"open": Decimal("1921.0"), "high": Decimal("1922.0"),
         "low": Decimal("1918.0"), "close": Decimal("1919.0")},
        {"open": Decimal("1918.5"), "high": Decimal("1923.0"),
         "low": Decimal("1918.0"), "close": Decimal("1921.5")},
    ]
    assert detect_engulfing(bars) == "bullish"


def test_detect_engulfing_bearish():
    # prev bullish (1919→1921), curr bearish engulfs: open>1921, close<1919
    bars = [
        {"open": Decimal("1919.0"), "high": Decimal("1922.0"),
         "low": Decimal("1918.0"), "close": Decimal("1921.0")},
        {"open": Decimal("1921.5"), "high": Decimal("1922.0"),
         "low": Decimal("1916.0"), "close": Decimal("1918.5")},
    ]
    assert detect_engulfing(bars) == "bearish"


def test_detect_engulfing_requires_two_bars():
    bars = [{"open": Decimal("1920.0"), "high": Decimal("1922.0"),
             "low": Decimal("1918.0"), "close": Decimal("1921.0")}]
    assert detect_engulfing(bars) is None


# --- DB tests ---

@pytest.mark.asyncio
async def test_run_pattern_detector_creates_alert_for_pin_bar(db_session):
    t = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
    db_session.add(PriceBar(
        time=t, symbol="XAUUSD", timeframe=Timeframe.H1,
        open=Decimal("1920.0"), high=Decimal("1921.0"),
        low=Decimal("1915.0"), close=Decimal("1920.5"),
    ))
    await db_session.commit()

    await run_pattern_detector(db_session, make_tick())

    result = await db_session.execute(select(Alert).where(Alert.type == "pattern_alert"))
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert alerts[0].trigger_data["pattern"] == "pin_bar"
    assert alerts[0].trigger_data["direction"] == "bullish"
    assert alerts[0].trigger_data["timeframe"] == "H1"


@pytest.mark.asyncio
async def test_run_pattern_detector_deduplicates_within_4_hours(db_session):
    t = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
    db_session.add(PriceBar(
        time=t, symbol="XAUUSD", timeframe=Timeframe.H1,
        open=Decimal("1920.0"), high=Decimal("1921.0"),
        low=Decimal("1915.0"), close=Decimal("1920.5"),
    ))
    db_session.add(Alert(
        type="pattern_alert",
        message="Pin Bar (bullish) detected on H1",
        trigger_data={"pattern": "pin_bar", "direction": "bullish", "timeframe": "H1"},
        sent_at=datetime.now(timezone.utc) - timedelta(hours=1),
        acknowledged=False,
    ))
    await db_session.commit()

    await run_pattern_detector(db_session, make_tick())

    result = await db_session.execute(select(Alert).where(Alert.type == "pattern_alert"))
    alerts = result.scalars().all()
    assert len(alerts) == 1  # no new alert created


@pytest.mark.asyncio
async def test_run_pattern_detector_no_alert_when_no_bars(db_session):
    await run_pattern_detector(db_session, make_tick())
    result = await db_session.execute(select(Alert))
    assert result.scalars().all() == []
```

- [x] **Step 2: Run to confirm FAIL**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_pattern_detector.py -v
```
Expected: `FAILED` — `cannot import name 'detect_pin_bar' from 'services.pattern_detector'`

- [x] **Step 3: Create `api/services/pattern_detector.py`**

```python
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.price_bar import PriceBar, Timeframe
from models.alert import Alert
from schemas.price_tick import PriceTickSchema

PATTERN_ALERT_COOLDOWN_HOURS = 4


def detect_pin_bar(bars: list) -> Optional[str]:
    """Returns 'bullish', 'bearish', or None. bars: list of dicts with Decimal open/high/low/close."""
    if not bars:
        return None
    b = bars[-1]
    open_, high, low, close = b["open"], b["high"], b["low"], b["close"]
    body = abs(close - open_)
    candle_range = high - low
    if candle_range == 0:
        return None
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low
    if lower_wick >= 2 * body and lower_wick >= Decimal("0.6") * candle_range:
        return "bullish"
    if upper_wick >= 2 * body and upper_wick >= Decimal("0.6") * candle_range:
        return "bearish"
    return None


def detect_engulfing(bars: list) -> Optional[str]:
    """Returns 'bullish', 'bearish', or None. Requires at least 2 bars."""
    if len(bars) < 2:
        return None
    prev, curr = bars[-2], bars[-1]
    prev_open, prev_close = prev["open"], prev["close"]
    curr_open, curr_close = curr["open"], curr["close"]
    if prev_close < prev_open and curr_close > prev_open and curr_open < prev_close:
        return "bullish"
    if prev_close > prev_open and curr_close < prev_open and curr_open > prev_close:
        return "bearish"
    return None


async def run_pattern_detector(session: AsyncSession, tick: PriceTickSchema) -> None:
    for tf in [Timeframe.H1, Timeframe.H4]:
        await _check_timeframe(session, tick.symbol, tf)
    await session.commit()


async def _check_timeframe(session: AsyncSession, symbol: str, tf: Timeframe) -> None:
    result = await session.execute(
        select(PriceBar)
        .where(PriceBar.symbol == symbol, PriceBar.timeframe == tf)
        .order_by(PriceBar.time.desc())
        .limit(2)
    )
    rows = list(reversed(result.scalars().all()))
    if not rows:
        return
    bars = [{"open": r.open, "high": r.high, "low": r.low, "close": r.close} for r in rows]

    for pattern_name, direction in [("pin_bar", detect_pin_bar(bars)), ("engulfing", detect_engulfing(bars))]:
        if direction is None:
            continue
        if await _is_duplicate(session, tf.value, pattern_name, direction):
            continue
        session.add(Alert(
            type="pattern_alert",
            message=f"{pattern_name.replace('_', ' ').title()} ({direction}) detected on {tf.value}",
            trigger_data={
                "pattern": pattern_name,
                "direction": direction,
                "timeframe": tf.value,
                "open": str(rows[-1].open),
                "high": str(rows[-1].high),
                "low": str(rows[-1].low),
                "close": str(rows[-1].close),
            },
            sent_at=datetime.now(timezone.utc),
            acknowledged=False,
        ))


async def _is_duplicate(session: AsyncSession, timeframe: str, pattern: str, direction: str) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=PATTERN_ALERT_COOLDOWN_HOURS)
    result = await session.execute(
        select(Alert).where(Alert.type == "pattern_alert", Alert.sent_at >= cutoff)
    )
    for alert in result.scalars().all():
        td = alert.trigger_data or {}
        if (td.get("pattern") == pattern and
                td.get("direction") == direction and
                td.get("timeframe") == timeframe):
            return True
    return False
```

- [x] **Step 4: Run tests — expect PASS**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_pattern_detector.py -v
```
Expected: `9 passed`

- [x] **Step 5: Run full suite**

```bash
/Users/nick/.venv/bin/python -m pytest tests/ -v
```
Expected: all pass.

- [x] **Step 6: Commit**

```bash
git add api/services/pattern_detector.py tests/test_pattern_detector.py
git commit -m "feat: add PatternDetector service (pin bar + engulfing)"
```

---

## Task 4: Wire PatternDetector + pattern_win_rate Insight

**Files:**
- Modify: `api/routers/price_tick.py`
- Modify: `api/services/insight_engine.py`
- Create: `tests/test_pattern_wire_up.py`

- [x] **Step 1: Write the failing tests**

`tests/test_pattern_wire_up.py`:
```python
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import select

from models.alert import Alert
from models.insight import Insight
from models.price_bar import PriceBar, Timeframe
from models.trade import Trade, Direction, OrderState, OrderType

# bullish pin bar OHLCV: lower_wick=5.0, body=0.5, range=6.0
PIN_BAR_TICK = {
    "timestamp": "2026-05-18T10:00:00Z",
    "symbol": "XAUUSD",
    "account": {
        "equity": 10000, "balance": 10000,
        "margin": 0, "free_margin": 10000, "floating_pl": 0,
    },
    "bars": {
        "H1": {"open": 1920.0, "high": 1921.0, "low": 1915.0, "close": 1920.5, "volume": 100},
    },
}


@pytest.mark.asyncio
async def test_price_tick_creates_pattern_alert_for_pin_bar(client, db_session):
    response = await client.post("/api/price-tick", json=PIN_BAR_TICK)
    assert response.status_code == 200

    result = await db_session.execute(select(Alert).where(Alert.type == "pattern_alert"))
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert alerts[0].trigger_data["pattern"] == "pin_bar"
    assert alerts[0].trigger_data["direction"] == "bullish"


@pytest.mark.asyncio
async def test_pattern_win_rate_insight_created(db_session):
    from services.insight_engine import run_insight_engine

    # Insert 10 winning trades each with a matching H1 pin bar
    for i in range(10):
        t = datetime(2026, 5, i + 1, 10, 0, tzinfo=timezone.utc)
        db_session.add(PriceBar(
            time=t, symbol="XAUUSD", timeframe=Timeframe.H1,
            open=Decimal("1920.0"), high=Decimal("1921.0"),
            low=Decimal("1915.0"), close=Decimal("1920.5"),
        ))
        db_session.add(Trade(
            id=uuid.uuid4(), ticket=1000 + i, symbol="XAUUSD",
            direction=Direction.buy, order_type=OrderType.market,
            order_state=OrderState.filled, is_paper=False,
            open_price=Decimal("1920.0"), close_price=Decimal("1921.0"),
            profit=Decimal("10.0"),
            open_time=t, close_time=t + timedelta(hours=2),
        ))
    await db_session.commit()

    await run_insight_engine(db_session)

    result = await db_session.execute(
        select(Insight).where(Insight.type == "pattern_win_rate", Insight.is_active == True)
    )
    insights = result.scalars().all()
    assert len(insights) == 1
    assert insights[0].confidence >= 0.6
    assert insights[0].sample_size == 10
    assert "pin_bar" in insights[0].description
```

- [x] **Step 2: Run to confirm FAIL**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_pattern_wire_up.py -v
```
Expected: `FAILED` — pattern_alert not created (router doesn't call pattern_detector yet), pattern_win_rate insight not found.

- [x] **Step 3: Update `api/routers/price_tick.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from schemas.price_tick import PriceTickSchema
from services.price_handler import save_price_tick
from services.alert_manager import check_equity_buffer
from services.pattern_detector import run_pattern_detector

router = APIRouter(prefix="/api", tags=["price-tick"])


@router.post("/price-tick")
async def receive_price_tick(
    tick: PriceTickSchema,
    session: AsyncSession = Depends(get_session),
):
    await save_price_tick(session, tick)
    await check_equity_buffer(session, tick)
    await run_pattern_detector(session, tick)
    return {"status": "saved", "timestamp": tick.timestamp.isoformat()}
```

- [x] **Step 4: Update `api/services/insight_engine.py`** — add `_compute_pattern_win_rate` and call it from `run_insight_engine`

Replace the full file content:
```python
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import pandas as pd

from models.trade import Trade, OrderState
from models.insight import Insight
from models.price_bar import PriceBar, Timeframe
from services.pattern_detector import detect_pin_bar, detect_engulfing

MIN_SAMPLE_SIZE = 10
MIN_CONFIDENCE = 0.6


async def run_insight_engine(session: AsyncSession) -> None:
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.order_state == OrderState.filled,
            Trade.open_time.isnot(None),
            Trade.close_time.isnot(None),
            Trade.profit.isnot(None),
        )
    )
    trades = result.scalars().all()
    if not trades:
        return

    df = pd.DataFrame([{
        "open_time": t.open_time,
        "profit": float(t.profit),
    } for t in trades])

    df["is_win"] = df["profit"] > 0
    df["hour"] = pd.to_datetime(df["open_time"], utc=True).dt.hour

    await _compute_time_bias(session, df)
    await _compute_session_bias(session, df)
    await _compute_pattern_win_rate(session, trades)
    await session.commit()


async def _compute_time_bias(session: AsyncSession, df: pd.DataFrame) -> None:
    hourly = df.groupby("hour").agg(
        trades=("is_win", "count"),
        win_rate=("is_win", "mean"),
    ).reset_index()

    loss_hours = hourly[
        (hourly["trades"] >= MIN_SAMPLE_SIZE) &
        (hourly["win_rate"] <= (1.0 - MIN_CONFIDENCE))
    ]
    if loss_hours.empty:
        return

    worst = loss_hours.loc[loss_hours["win_rate"].idxmin()]
    sample_size = int(worst["trades"])
    confidence = float(1.0 - worst["win_rate"])

    old = await session.execute(
        select(Insight).where(Insight.type == "time_bias", Insight.is_active == True)
    )
    for ins in old.scalars().all():
        ins.is_active = False

    data = json.loads(hourly.to_json(orient="records"))
    session.add(Insight(
        type="time_bias",
        description=(
            f"{confidence:.0%} of your trades at {int(worst['hour']):02d}:00 UTC "
            f"result in a loss ({sample_size} trades)"
        ),
        confidence=confidence,
        sample_size=sample_size,
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data=data,
    ))


def _assign_session(hour: int) -> str:
    if 7 <= hour < 16:
        return "London"
    if 13 <= hour < 22:
        return "NY"
    return "Asia"  # hours 0-6 and 22-23: post-NY pre-Asia overlap treated as Asia


async def _compute_session_bias(session: AsyncSession, df: pd.DataFrame) -> None:
    df = df.copy()
    df["session"] = df["hour"].apply(_assign_session)

    stats = df.groupby("session").agg(
        trades=("is_win", "count"),
        win_rate=("is_win", "mean"),
    ).reset_index()

    qualified = stats[stats["trades"] >= MIN_SAMPLE_SIZE]
    if qualified.empty:
        return

    best = qualified.loc[qualified["win_rate"].idxmax()]
    if float(best["win_rate"]) < MIN_CONFIDENCE:
        return

    sample_size = int(best["trades"])
    confidence = float(best["win_rate"])

    old = await session.execute(
        select(Insight).where(Insight.type == "session_bias", Insight.is_active == True)
    )
    for ins in old.scalars().all():
        ins.is_active = False

    data = json.loads(stats.to_json(orient="records"))
    session.add(Insight(
        type="session_bias",
        description=(
            f"Your win rate is highest during {best['session']} session "
            f"({confidence:.0%} from {sample_size} trades)"
        ),
        confidence=confidence,
        sample_size=sample_size,
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data=data,
    ))


async def _compute_pattern_win_rate(session: AsyncSession, trades: list) -> None:
    records = []
    for trade in trades:
        hour_start = trade.open_time.replace(minute=0, second=0, microsecond=0)
        bar_res = await session.execute(
            select(PriceBar).where(
                PriceBar.symbol == trade.symbol,
                PriceBar.timeframe == Timeframe.H1,
                PriceBar.time >= hour_start,
                PriceBar.time < hour_start + timedelta(hours=1),
            ).order_by(PriceBar.time.desc()).limit(1)
        )
        bar = bar_res.scalar_one_or_none()
        if bar is None:
            continue

        prev_res = await session.execute(
            select(PriceBar).where(
                PriceBar.symbol == trade.symbol,
                PriceBar.timeframe == Timeframe.H1,
                PriceBar.time >= hour_start - timedelta(hours=1),
                PriceBar.time < hour_start,
            ).order_by(PriceBar.time.desc()).limit(1)
        )
        prev_bar = prev_res.scalar_one_or_none()

        bar_dict = {"open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close}
        bars = []
        if prev_bar:
            bars.append({"open": prev_bar.open, "high": prev_bar.high,
                         "low": prev_bar.low, "close": prev_bar.close})
        bars.append(bar_dict)

        pin_dir = detect_pin_bar(bars)
        eng_dir = detect_engulfing(bars)
        if pin_dir:
            records.append({"pattern": "pin_bar", "direction": pin_dir,
                            "is_win": float(trade.profit) > 0})
        elif eng_dir:
            records.append({"pattern": "engulfing", "direction": eng_dir,
                            "is_win": float(trade.profit) > 0})

    if not records:
        return

    df = pd.DataFrame(records)
    grouped = df.groupby(["pattern", "direction"]).agg(
        trades=("is_win", "count"),
        win_rate=("is_win", "mean"),
    ).reset_index()

    old = await session.execute(
        select(Insight).where(Insight.type == "pattern_win_rate", Insight.is_active == True)
    )
    for ins in old.scalars().all():
        ins.is_active = False

    for _, row in grouped.iterrows():
        if int(row["trades"]) < MIN_SAMPLE_SIZE or float(row["win_rate"]) < MIN_CONFIDENCE:
            continue
        session.add(Insight(
            type="pattern_win_rate",
            description=(
                f"Trades opened after a {row['direction']} "
                f"{str(row['pattern']).replace('_', ' ')} on H1 "
                f"have a {float(row['win_rate']):.0%} win rate ({int(row['trades'])} trades)"
            ),
            confidence=float(row["win_rate"]),
            sample_size=int(row["trades"]),
            discovered_at=datetime.now(timezone.utc),
            is_active=True,
            data={
                "pattern": row["pattern"],
                "direction": row["direction"],
                "timeframe": "H1",
                "win_rate": float(row["win_rate"]),
            },
        ))
```

- [x] **Step 5: Run tests — expect PASS**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_pattern_wire_up.py -v
```
Expected: `2 passed`

- [x] **Step 6: Run full suite**

```bash
/Users/nick/.venv/bin/python -m pytest tests/ -v
```
Expected: all pass.

- [x] **Step 7: Commit**

```bash
git add api/routers/price_tick.py api/services/insight_engine.py tests/test_pattern_wire_up.py
git commit -m "feat: wire PatternDetector into price_tick router and add pattern_win_rate insight"
```

---

## Task 5: Frontend Scaffold

Creates the React + Vite + TailwindCSS project. No components yet — just verify `npm run dev` starts successfully.

**Files:** `frontend/package.json`, `frontend/vite.config.js`, `frontend/tailwind.config.js`, `frontend/postcss.config.js`, `frontend/index.html`, `frontend/src/main.jsx`, `frontend/src/index.css`

- [x] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "trade-signal-frontend",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host 0.0.0.0",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.47",
    "tailwindcss": "^3.4.14",
    "vite": "^5.4.10"
  }
}
```

- [x] **Step 2: Create `frontend/vite.config.js`**

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
  },
})
```

- [x] **Step 3: Create `frontend/tailwind.config.js`**

```js
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: { extend: {} },
  plugins: [],
}
```

- [x] **Step 4: Create `frontend/postcss.config.js`**

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

- [x] **Step 5: Create `frontend/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Trade Signal Partner</title>
  </head>
  <body class="bg-gray-950">
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

- [x] **Step 6: Create `frontend/src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [x] **Step 7: Create `frontend/src/main.jsx`**

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <div className="p-8 text-white">Trade Signal Partner — loading...</div>
  </React.StrictMode>
)
```

- [x] **Step 8: Install dependencies and verify dev server starts**

```bash
cd /Users/nick/2_SideProjects/trade-signal/frontend
npm install
npm run dev
```
Expected output includes: `Local: http://localhost:3000/` and no errors. Open browser to verify white text on dark background appears. Stop with Ctrl+C.

- [x] **Step 9: Commit**

```bash
cd /Users/nick/2_SideProjects/trade-signal
git add frontend/
git commit -m "feat: scaffold React + Vite + TailwindCSS frontend"
```

---

## Task 6: usePolling Hook + App.jsx

**Files:**
- Create: `frontend/src/hooks/usePolling.js`
- Create: `frontend/src/App.jsx`
- Modify: `frontend/src/main.jsx`

- [x] **Step 1: Create `frontend/src/hooks/usePolling.js`**

```js
import { useState, useEffect, useCallback } from 'react'

export function usePolling(fetcher, intervalMs = 30000) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [tick, setTick] = useState(0)

  const refetch = useCallback(() => setTick(t => t + 1), [])

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      try {
        const result = await fetcher()
        if (!cancelled) {
          setData(result)
          setLastUpdated(new Date())
          setError(null)
        }
      } catch (e) {
        if (!cancelled) setError(e)
      }
    }
    run()
    const id = setInterval(run, intervalMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [fetcher, intervalMs, tick])

  return { data, error, lastUpdated, refetch }
}
```

- [x] **Step 2: Create `frontend/src/App.jsx`**

At this stage, App renders placeholder divs for each section. Components are wired in Tasks 7–9.

```jsx
import { useCallback } from 'react'
import { usePolling } from './hooks/usePolling'

const API = 'http://localhost:8000'

async function get(path) {
  const res = await fetch(API + path)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export default function App() {
  const fetchAccount = useCallback(() => get('/api/account'), [])
  const fetchAlerts = useCallback(() => get('/api/alerts'), [])
  const fetchInsights = useCallback(() => get('/api/insights'), [])
  const fetchOpen = useCallback(() => get('/api/trades?state=open'), [])
  const fetchClosed = useCallback(() => get('/api/trades?state=closed&limit=20'), [])

  const account = usePolling(fetchAccount)
  const alerts = usePolling(fetchAlerts)
  const insights = usePolling(fetchInsights)
  const openTrades = usePolling(fetchOpen)
  const closedTrades = usePolling(fetchClosed)

  async function acknowledgeAlert(id) {
    await fetch(`${API}/api/alerts/${id}/acknowledge`, { method: 'PATCH' })
    alerts.refetch()
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-4 space-y-4">
      <div className="bg-gray-900 rounded-lg p-4 text-sm text-gray-400">
        Account: {account.data ? JSON.stringify(account.data) : account.error ? 'error' : 'loading...'}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-gray-900 rounded-lg p-4 text-sm text-gray-400">
          Alerts: {alerts.data?.length ?? '...'}
        </div>
        <div className="bg-gray-900 rounded-lg p-4 text-sm text-gray-400">
          Insights: {insights.data?.length ?? '...'}
        </div>
      </div>
      <div className="bg-gray-900 rounded-lg p-4 text-sm text-gray-400">
        Open trades: {openTrades.data?.length ?? '...'}
      </div>
      <div className="bg-gray-900 rounded-lg p-4 text-sm text-gray-400">
        Closed trades: {closedTrades.data?.length ?? '...'}
      </div>
    </div>
  )
}
```

- [x] **Step 3: Update `frontend/src/main.jsx`** to use App

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
```

- [x] **Step 4: Verify**

```bash
cd /Users/nick/2_SideProjects/trade-signal/frontend
npm run dev
```
Open `http://localhost:3000`. Confirm 5 gray boxes appear and that the account/alerts/insights boxes show either data or "loading..." / "error" (depending on whether the API is running). No console errors about missing modules.

- [x] **Step 5: Commit**

```bash
cd /Users/nick/2_SideProjects/trade-signal
git add frontend/src/
git commit -m "feat: add usePolling hook and App.jsx shell"
```

---

## Task 7: AccountBar Component

**Files:**
- Create: `frontend/src/components/AccountBar.jsx`
- Modify: `frontend/src/App.jsx`

- [x] **Step 1: Create `frontend/src/components/AccountBar.jsx`**

```jsx
import { useState, useEffect } from 'react'

function fmt(v, decimals = 2) {
  if (v == null) return '—'
  return Number(v).toFixed(decimals)
}

export default function AccountBar({ data, error, lastUpdated }) {
  const [secs, setSecs] = useState(0)

  useEffect(() => {
    const id = setInterval(() => {
      setSecs(lastUpdated ? Math.floor((new Date() - lastUpdated) / 1000) : 0)
    }, 1000)
    return () => clearInterval(id)
  }, [lastUpdated])

  const floatPL = data?.floating_pl != null ? Number(data.floating_pl) : null

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Account</h2>
        <span className={`text-xs ${error ? 'text-red-400' : 'text-gray-500'}`}>
          {error ? 'Data may be stale' : lastUpdated ? `Updated ${secs}s ago` : 'Loading...'}
        </span>
      </div>
      <div className="grid grid-cols-5 gap-6">
        {[
          { label: 'Equity', value: fmt(data?.equity) },
          { label: 'Balance', value: fmt(data?.balance) },
          { label: 'Margin', value: fmt(data?.margin) },
          { label: 'Free Margin', value: fmt(data?.free_margin) },
          { label: 'Float P/L', value: fmt(data?.floating_pl), colored: true },
        ].map(({ label, value, colored }) => (
          <div key={label}>
            <p className="text-xs text-gray-500 mb-0.5">{label}</p>
            <p className={`text-xl font-mono font-semibold ${
              colored && floatPL != null
                ? floatPL >= 0 ? 'text-green-400' : 'text-red-400'
                : 'text-white'
            }`}>
              ${value}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [x] **Step 2: Update `frontend/src/App.jsx`** — replace the account placeholder div with the component

Add import at the top:
```jsx
import AccountBar from './components/AccountBar'
```

Replace:
```jsx
      <div className="bg-gray-900 rounded-lg p-4 text-sm text-gray-400">
        Account: {account.data ? JSON.stringify(account.data) : account.error ? 'error' : 'loading...'}
      </div>
```
With:
```jsx
      <AccountBar data={account.data} error={account.error} lastUpdated={account.lastUpdated} />
```

- [x] **Step 3: Verify**

Start the API (`docker compose up -d`) and the frontend (`npm run dev`). Open `http://localhost:3000`. Confirm the account bar shows 5 labeled values. If the API has no data yet, all values show `—`. The "Updated Xs ago" counter should tick up each second.

- [x] **Step 4: Commit**

```bash
cd /Users/nick/2_SideProjects/trade-signal
git add frontend/src/components/AccountBar.jsx frontend/src/App.jsx
git commit -m "feat: add AccountBar component"
```

---

## Task 8: AlertsPanel + InsightsPanel Components

**Files:**
- Create: `frontend/src/components/AlertsPanel.jsx`
- Create: `frontend/src/components/InsightsPanel.jsx`
- Modify: `frontend/src/App.jsx`

- [x] **Step 1: Create `frontend/src/components/AlertsPanel.jsx`**

```jsx
const TYPE_COLORS = {
  equity_buffer: 'bg-red-900 text-red-200',
  double_down: 'bg-yellow-900 text-yellow-200',
  consecutive_loss: 'bg-orange-900 text-orange-200',
  pattern_alert: 'bg-blue-900 text-blue-200',
}

function AlertRow({ alert, onAcknowledge, muted }) {
  const colorClass = TYPE_COLORS[alert.type] ?? 'bg-gray-800 text-gray-200'
  return (
    <div className={`flex items-start gap-2 p-2 rounded ${muted ? 'opacity-40' : ''}`}>
      <span className={`text-xs px-1.5 py-0.5 rounded font-mono shrink-0 ${colorClass}`}>
        {alert.type}
      </span>
      <p className="text-sm text-gray-300 flex-1 min-w-0 break-words">{alert.message}</p>
      {!muted && onAcknowledge && (
        <button
          onClick={() => onAcknowledge(alert.id)}
          className="text-xs text-gray-500 hover:text-white shrink-0 px-1"
        >
          Ack
        </button>
      )}
    </div>
  )
}

export default function AlertsPanel({ data, error, onAcknowledge }) {
  const alerts = data ?? []
  const unacked = alerts.filter(a => !a.acknowledged)
  const acked = alerts.filter(a => a.acknowledged)

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Alerts</h2>
        {unacked.length > 0 && (
          <span className="bg-red-600 text-white text-xs font-bold px-2 py-0.5 rounded-full">
            {unacked.length}
          </span>
        )}
        {error && <span className="text-xs text-red-400 ml-auto">Stale</span>}
      </div>
      <div className="space-y-1 max-h-72 overflow-y-auto">
        {unacked.map(alert => (
          <AlertRow key={alert.id} alert={alert} onAcknowledge={onAcknowledge} />
        ))}
        {acked.map(alert => (
          <AlertRow key={alert.id} alert={alert} muted />
        ))}
        {alerts.length === 0 && (
          <p className="text-sm text-gray-600">No alerts</p>
        )}
      </div>
    </div>
  )
}
```

- [x] **Step 2: Create `frontend/src/components/InsightsPanel.jsx`**

```jsx
const TYPE_COLORS = {
  time_bias: 'bg-purple-900 text-purple-200',
  session_bias: 'bg-indigo-900 text-indigo-200',
  pattern_win_rate: 'bg-teal-900 text-teal-200',
}

export default function InsightsPanel({ data, error }) {
  const insights = (data ?? []).slice().sort((a, b) => b.confidence - a.confidence)

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Insights</h2>
        {error && <span className="text-xs text-red-400 ml-auto">Stale</span>}
      </div>
      <div className="space-y-2 max-h-72 overflow-y-auto">
        {insights.map(insight => (
          <div key={insight.id} className="p-2 rounded bg-gray-800">
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${TYPE_COLORS[insight.type] ?? 'bg-gray-700 text-gray-200'}`}>
                {insight.type}
              </span>
              <span className="text-xs text-green-400 font-semibold ml-auto">
                {(insight.confidence * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-sm text-gray-300">{insight.description}</p>
            <p className="text-xs text-gray-600 mt-0.5">n={insight.sample_size}</p>
          </div>
        ))}
        {insights.length === 0 && (
          <p className="text-sm text-gray-600">No insights yet</p>
        )}
      </div>
    </div>
  )
}
```

- [x] **Step 3: Update `frontend/src/App.jsx`** — replace the alerts/insights placeholder divs

Add imports:
```jsx
import AlertsPanel from './components/AlertsPanel'
import InsightsPanel from './components/InsightsPanel'
```

Replace the grid section:
```jsx
      <div className="grid grid-cols-2 gap-4">
        <AlertsPanel data={alerts.data} error={alerts.error} onAcknowledge={acknowledgeAlert} />
        <InsightsPanel data={insights.data} error={insights.error} />
      </div>
```

- [x] **Step 4: Verify**

With the API running, open `http://localhost:3000`. The two-column row should show AlertsPanel on the left and InsightsPanel on the right. If no data, both show their "No alerts" / "No insights yet" empty states. If there are alerts, the Ack button should work (clicking it makes the alert move to the muted section on next render).

- [x] **Step 5: Commit**

```bash
cd /Users/nick/2_SideProjects/trade-signal
git add frontend/src/components/AlertsPanel.jsx frontend/src/components/InsightsPanel.jsx frontend/src/App.jsx
git commit -m "feat: add AlertsPanel and InsightsPanel components"
```

---

## Task 9: OpenPositions + ClosedTrades Components

**Files:**
- Create: `frontend/src/components/OpenPositions.jsx`
- Create: `frontend/src/components/ClosedTrades.jsx`
- Modify: `frontend/src/App.jsx`

- [x] **Step 1: Create `frontend/src/components/OpenPositions.jsx`**

```jsx
function fmt(v, d = 5) {
  if (v == null) return '—'
  return Number(v).toFixed(d)
}

export default function OpenPositions({ data, error }) {
  const trades = data ?? []
  const real = trades.filter(t => !t.is_paper)

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Open Positions
        </h2>
        {real.length > 0 && (
          <span className="text-xs text-gray-500">{real.length} open</span>
        )}
        {error && <span className="text-xs text-red-400 ml-auto">Stale</span>}
      </div>
      {real.length === 0 ? (
        <p className="text-sm text-gray-600">No open positions</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 text-left border-b border-gray-800">
              <th className="pb-2 pr-4">Ticket</th>
              <th className="pb-2 pr-4">Dir</th>
              <th className="pb-2 pr-4">Real Entry</th>
              <th className="pb-2 pr-4">Paper Entry</th>
              <th className="pb-2 pr-4">Paper SL</th>
              <th className="pb-2">Paper TP</th>
            </tr>
          </thead>
          <tbody>
            {real.map(t => {
              const paper = trades.find(p => p.is_paper && p.ticket === t.ticket)
              return (
                <tr key={t.id} className="border-b border-gray-800 last:border-0">
                  <td className="py-2 pr-4 font-mono text-gray-300">{t.ticket}</td>
                  <td className={`py-2 pr-4 font-semibold ${t.direction === 'buy' ? 'text-green-400' : 'text-red-400'}`}>
                    {t.direction?.toUpperCase() ?? '—'}
                  </td>
                  <td className="py-2 pr-4 font-mono">{fmt(t.open_price)}</td>
                  <td className="py-2 pr-4 font-mono">{fmt(paper?.open_price)}</td>
                  <td className="py-2 pr-4 font-mono text-red-400">{fmt(paper?.sl)}</td>
                  <td className="py-2 font-mono text-green-400">{fmt(paper?.tp)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
```

- [x] **Step 2: Create `frontend/src/components/ClosedTrades.jsx`**

```jsx
function fmtPL(v) {
  if (v == null) return '—'
  const n = Number(v)
  return (n >= 0 ? '+' : '') + n.toFixed(2)
}

function plColor(v) {
  if (v == null) return 'text-gray-500'
  return Number(v) >= 0 ? 'text-green-400' : 'text-red-400'
}

export default function ClosedTrades({ data, error }) {
  const trades = data ?? []
  const real = trades.filter(t => !t.is_paper)

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Recent Closed Trades
        </h2>
        {error && <span className="text-xs text-red-400 ml-auto">Stale</span>}
      </div>
      {real.length === 0 ? (
        <p className="text-sm text-gray-600">No closed trades yet</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 text-left border-b border-gray-800">
              <th className="pb-2 pr-4">Ticket</th>
              <th className="pb-2 pr-4">Dir</th>
              <th className="pb-2 pr-4">Real P/L</th>
              <th className="pb-2 pr-4">Paper P/L</th>
              <th className="pb-2">Diff</th>
            </tr>
          </thead>
          <tbody>
            {real.map(t => {
              const paper = trades.find(p => p.is_paper && p.ticket === t.ticket)
              const realPL = t.profit != null ? Number(t.profit) : null
              const paperPL = paper?.profit != null ? Number(paper.profit) : null
              const diff = realPL != null && paperPL != null ? paperPL - realPL : null
              return (
                <tr key={t.id} className="border-b border-gray-800 last:border-0">
                  <td className="py-2 pr-4 font-mono text-gray-300">{t.ticket}</td>
                  <td className={`py-2 pr-4 font-semibold ${t.direction === 'buy' ? 'text-green-400' : 'text-red-400'}`}>
                    {t.direction?.toUpperCase() ?? '—'}
                  </td>
                  <td className={`py-2 pr-4 font-mono ${plColor(realPL)}`}>{fmtPL(realPL)}</td>
                  <td className={`py-2 pr-4 font-mono ${plColor(paperPL)}`}>{fmtPL(paperPL)}</td>
                  <td className={`py-2 font-mono ${plColor(diff)}`}>{fmtPL(diff)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
```

- [x] **Step 3: Update `frontend/src/App.jsx`** — replace placeholder divs with components

Add imports:
```jsx
import OpenPositions from './components/OpenPositions'
import ClosedTrades from './components/ClosedTrades'
```

Replace the two remaining placeholder divs:
```jsx
      <OpenPositions data={openTrades.data} error={openTrades.error} />
      <ClosedTrades data={closedTrades.data} error={closedTrades.error} />
```

- [x] **Step 4: Verify**

With the API running, open `http://localhost:3000`. The full page should render all 5 sections with no console errors. Test empty states (no data), and if you have trades in the DB, verify real/paper pairing by ticket works in both tables.

- [x] **Step 5: Commit**

```bash
cd /Users/nick/2_SideProjects/trade-signal
git add frontend/src/components/OpenPositions.jsx frontend/src/components/ClosedTrades.jsx frontend/src/App.jsx
git commit -m "feat: add OpenPositions and ClosedTrades components"
```

---

## Task 10: Docker Frontend Service

**Files:**
- Create: `frontend/Dockerfile`
- Modify: `docker-compose.yml`

- [x] **Step 1: Create `frontend/Dockerfile`**

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]
```

- [x] **Step 2: Update `docker-compose.yml`** — add frontend service

```yaml
services:
  db:
    image: timescale/timescaledb:2.17.2-pg16
    environment:
      POSTGRES_DB: tradesignal
      POSTGRES_USER: tradesignal
      POSTGRES_PASSWORD: tradesignal
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tradesignal -d tradesignal"]
      interval: 5s
      timeout: 5s
      retries: 10

  api:
    build: ./api
    ports:
      - "8000:8000"
    env_file: .env
    command: ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./api:/app

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - api
    volumes:
      - ./frontend:/app
      - /app/node_modules

volumes:
  pgdata:
```

Note: The `- /app/node_modules` volume prevents the host's `frontend/node_modules` from overwriting the container's npm-installed modules.

- [x] **Step 3: Build and start full stack**

```bash
docker compose up --build -d
```
Expected: db, api, and frontend containers all start. No build errors.

- [x] **Step 4: Smoke test**

```bash
# API health
curl http://localhost:8000/health
# Expected: {"status":"ok"}

# Dashboard loads
curl -I http://localhost:3000
# Expected: HTTP/1.1 200 OK
```

Open `http://localhost:3000` in a browser. The dashboard should load and poll the API. Check browser console for errors — there should be none.

- [x] **Step 5: Run full backend test suite one final time**

```bash
/Users/nick/.venv/bin/python -m pytest tests/ -v
```
Expected: all pass.

- [x] **Step 6: Commit**

```bash
cd /Users/nick/2_SideProjects/trade-signal
git add frontend/Dockerfile docker-compose.yml
git commit -m "feat: add frontend Docker service to docker-compose.yml"
```

---

## Done

Phase 3 is complete when:
- All backend tests pass (`pytest tests/ -v`)
- `docker compose up --build -d` starts all three services without errors
- `http://localhost:3000` loads the dashboard and shows all 5 sections
- Acknowledge button on alerts works (click → alert moves to muted section)
- Polling updates data every 30s (observe "Updated Xs ago" counting up and resetting)

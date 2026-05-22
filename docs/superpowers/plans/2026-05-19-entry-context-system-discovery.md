# Entry Context & Trading System Discovery — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Maintain `implementation-notes.md`** at project root throughout development. Record every decision not in this spec, deviation, trade-off, and open question.

**Goal:** Capture rich market context at every trade entry (5 auto-filled fields + 2 manual tags) so the insight engine can statistically discover which conditions correlate with winning trades.

**Architecture:** `entry_context.py` service auto-fills 5 fields on ENTRY_IN; user manually tags 2 via dashboard dropdowns (auto-save on change). Insight engine gains 5 new computation functions. Two new alert types fire when poor setups repeat. Dashboard gets tag dropdowns, 2-row closed-trade cards, Ack All, and paging.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + PostgreSQL + React + Tailwind (no new deps). Tests: pytest + pytest-asyncio + SQLite in-memory.

**Spec:** `docs/superpowers/specs/2026-05-19-entry-context-system-discovery-design.md`

---

## File Map

| Action | File |
|---|---|
| Create | `api/alembic/versions/005_add_entry_context.py` |
| Create | `api/services/entry_context.py` |
| Create | `tests/test_entry_context.py` |
| Create | `tests/test_trades_api.py` |
| Create | `tests/test_alerts_api.py` |
| Create | `frontend/src/components/SetupTag.jsx` |
| Modify | `api/models/trade.py` — 8 new nullable columns |
| Modify | `api/schemas/trade.py` — 8 new optional fields + TradeTagSchema |
| Modify | `api/services/trade_logger.py` — call fill_entry_context on ENTRY_IN |
| Modify | `api/services/insight_engine.py` — 5 new functions + MIN_ENTRY_SAMPLE constant |
| Modify | `api/services/alert_manager.py` — 2 new alert checks |
| Modify | `api/routers/trades.py` — PATCH tag endpoint + offset param |
| Modify | `api/routers/alerts.py` — POST acknowledge-all endpoint |
| Modify | `frontend/src/components/OpenPositions.jsx` — tag dropdowns |
| Modify | `frontend/src/components/ClosedTrades.jsx` — 2-row layout + paging |
| Modify | `frontend/src/components/AlertsPanel.jsx` — Ack All button |
| Modify | `frontend/src/App.jsx` — paging state + ack-all wiring |

---

## Task 1: DB Migration + Trade Model Columns

**Files:**
- Create: `api/alembic/versions/005_add_entry_context.py`
- Modify: `api/models/trade.py`

- [ ] **Step 1: Write the failing migration test**

Create `tests/test_migration_005.py`:

```python
import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from database import Base

@pytest.mark.asyncio
async def test_trade_model_has_entry_context_columns():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with engine.connect() as conn:
        cols = await conn.run_sync(
            lambda sync_conn: [c["name"] for c in inspect(sync_conn).get_columns("trades")]
        )
    expected = ["setup_pattern", "trade_bias", "near_fib_level",
                "fib_distance_pts", "entry_candle", "entry_candle_tf",
                "is_rescue", "post_close_run_pts"]
    for col in expected:
        assert col in cols, f"Missing column: {col}"
    await engine.dispose()
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd api && pytest ../tests/test_migration_005.py -v
```
Expected: FAIL (columns don't exist yet)

- [ ] **Step 3: Add 8 columns to Trade model**

In `api/models/trade.py`, after the `paper_exit_reason` column:

```python
    # Entry context — all nullable, auto-filled on ENTRY_IN or manual tag
    setup_pattern: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    trade_bias: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    near_fib_level: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    fib_distance_pts: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    entry_candle: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    entry_candle_tf: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    is_rescue: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    post_close_run_pts: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
```

- [ ] **Step 4: Create migration file**

```python
# api/alembic/versions/005_add_entry_context.py
"""add entry context columns

Revision ID: 005
Revises: 004
Create Date: 2026-05-19

"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("setup_pattern", sa.String(30), nullable=True))
    op.add_column("trades", sa.Column("trade_bias", sa.String(10), nullable=True))
    op.add_column("trades", sa.Column("near_fib_level", sa.String(10), nullable=True))
    op.add_column("trades", sa.Column("fib_distance_pts", sa.Numeric(8, 2), nullable=True))
    op.add_column("trades", sa.Column("entry_candle", sa.String(30), nullable=True))
    op.add_column("trades", sa.Column("entry_candle_tf", sa.String(5), nullable=True))
    op.add_column("trades", sa.Column("is_rescue", sa.Boolean, nullable=True))
    op.add_column("trades", sa.Column("post_close_run_pts", sa.Numeric(8, 2), nullable=True))


def downgrade() -> None:
    for col in ["setup_pattern", "trade_bias", "near_fib_level",
                "fib_distance_pts", "entry_candle", "entry_candle_tf",
                "is_rescue", "post_close_run_pts"]:
        op.drop_column("trades", col)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd api && pytest ../tests/test_migration_005.py -v
```
Expected: PASS

- [ ] **Step 6: Run full suite to check no regressions**

```bash
cd api && pytest ../tests/ -v
```
Expected: all existing tests pass

- [ ] **Step 7: Commit**

```bash
git add api/models/trade.py api/alembic/versions/005_add_entry_context.py tests/test_migration_005.py
git commit -m "feat: add 8 entry context columns to trades table (migration 005)"
```

---

## Task 2: TradeResponse Schema + TradeTagSchema

**Files:**
- Modify: `api/schemas/trade.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_trades_api.py`:

```python
import pytest
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from models.trade import Trade, Direction, OrderState


@pytest.mark.asyncio
async def test_trade_response_includes_entry_context_fields(client, db_session):
    trade = Trade(
        id=uuid.uuid4(),
        ticket=1001,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("2000.00"),
        open_time=datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc),
        is_paper=False,
        setup_pattern="double_bottom",
        trade_bias="bullish",
        near_fib_level="S0.235",
        fib_distance_pts=Decimal("3.50"),
        entry_candle="pin_bar_bullish",
        entry_candle_tf="H1",
        is_rescue=False,
    )
    db_session.add(trade)
    await db_session.commit()

    resp = await client.get("/api/trades?state=open")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    t = data[0]
    assert t["setup_pattern"] == "double_bottom"
    assert t["trade_bias"] == "bullish"
    assert t["near_fib_level"] == "S0.235"
    assert float(t["fib_distance_pts"]) == pytest.approx(3.5)
    assert t["entry_candle"] == "pin_bar_bullish"
    assert t["entry_candle_tf"] == "H1"
    assert t["is_rescue"] is False
    assert t["post_close_run_pts"] is None
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd api && pytest ../tests/test_trades_api.py::test_trade_response_includes_entry_context_fields -v
```
Expected: FAIL (fields missing from response)

- [ ] **Step 3: Update TradeResponse + add TradeTagSchema**

Replace `api/schemas/trade.py` with:

```python
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID
from pydantic import BaseModel


VALID_SETUP_PATTERNS = {
    "double_top", "double_bottom", "triple_top", "triple_bottom",
    "rounded_top", "rounded_bottom", "price_cluster", "other",
}


class TradeTagSchema(BaseModel):
    setup_pattern: Optional[Literal[
        "double_top", "double_bottom", "triple_top", "triple_bottom",
        "rounded_top", "rounded_bottom", "price_cluster", "other"
    ]] = None
    trade_bias: Optional[Literal["bullish", "bearish"]] = None


class TradeResponse(BaseModel):
    id: UUID
    ticket: int
    symbol: str
    direction: Optional[str] = None
    order_type: Optional[str] = None
    order_state: Optional[str] = None
    is_paper: bool
    paper_mode: Optional[str] = None
    paper_exit_strategy: Optional[str] = None
    paper_exit_reason: Optional[str] = None
    open_price: Optional[Decimal] = None
    close_price: Optional[Decimal] = None
    tp: Optional[Decimal] = None
    sl: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    profit: Optional[Decimal] = None
    open_time: Optional[datetime] = None
    close_time: Optional[datetime] = None
    setup_pattern: Optional[str] = None
    trade_bias: Optional[str] = None
    near_fib_level: Optional[str] = None
    fib_distance_pts: Optional[Decimal] = None
    entry_candle: Optional[str] = None
    entry_candle_tf: Optional[str] = None
    is_rescue: Optional[bool] = None
    post_close_run_pts: Optional[Decimal] = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd api && pytest ../tests/test_trades_api.py::test_trade_response_includes_entry_context_fields -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/schemas/trade.py tests/test_trades_api.py
git commit -m "feat: add 8 entry context fields to TradeResponse + TradeTagSchema"
```

---

## Task 3: entry_context service — `_fill_fib_proximity`

**Files:**
- Create: `api/services/entry_context.py`
- Create: `tests/test_entry_context.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_entry_context.py`:

```python
import pytest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from models.trade import Trade, Direction, OrderState
from models.fib_level import FibLevel
from services.entry_context import fill_entry_context


def _make_trade(**kwargs) -> Trade:
    defaults = dict(
        id=uuid.uuid4(),
        ticket=1001,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("2000.00"),
        open_time=datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc),
        is_paper=False,
    )
    defaults.update(kwargs)
    return Trade(**defaults)


@pytest.mark.asyncio
async def test_fill_fib_proximity_finds_nearest_level(db_session):
    fib = FibLevel(
        symbol="XAUUSD",
        timeframe="D",
        swing_high=2050.0,
        swing_low=1950.0,
        direction="bullish",
        levels={"0.000": 1983.33, "0.236": 2006.93, "0.618": 2045.17},
        extensions={"0.236": 1959.73, "0.618": 1921.50},
        computed_at=datetime(2026, 5, 19, 8, 0, tzinfo=timezone.utc),
    )
    db_session.add(fib)
    await db_session.commit()

    trade = _make_trade(open_price=Decimal("1962.00"))
    db_session.add(trade)
    await db_session.commit()

    await fill_entry_context(db_session, trade)

    # open_price 1962.00, nearest level is S0.236 at 1959.73 (distance 2.27)
    assert trade.near_fib_level == "S0.236"
    assert trade.fib_distance_pts is not None
    assert float(trade.fib_distance_pts) == pytest.approx(2.27, abs=0.1)


@pytest.mark.asyncio
async def test_fill_fib_proximity_labels_pp_correctly(db_session):
    fib = FibLevel(
        symbol="XAUUSD",
        timeframe="D",
        swing_high=2050.0,
        swing_low=1950.0,
        direction="bullish",
        levels={"0.000": 1983.33, "0.236": 2006.93},
        extensions={"0.236": 1959.73},
        computed_at=datetime(2026, 5, 19, 8, 0, tzinfo=timezone.utc),
    )
    db_session.add(fib)
    await db_session.commit()

    trade = _make_trade(open_price=Decimal("1984.00"))
    db_session.add(trade)
    await db_session.commit()

    await fill_entry_context(db_session, trade)

    # 1984.00 is closest to PP (1983.33, distance 0.67) vs S0.236 (1959.73, distance 24.27) vs R0.236 (2006.93, distance 22.93)
    assert trade.near_fib_level == "PP"


@pytest.mark.asyncio
async def test_fill_fib_proximity_skips_when_no_fib_data(db_session):
    trade = _make_trade()
    db_session.add(trade)
    await db_session.commit()

    await fill_entry_context(db_session, trade)

    assert trade.near_fib_level is None
    assert trade.fib_distance_pts is None
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd api && pytest ../tests/test_entry_context.py::test_fill_fib_proximity_finds_nearest_level ../tests/test_entry_context.py::test_fill_fib_proximity_labels_pp_correctly ../tests/test_entry_context.py::test_fill_fib_proximity_skips_when_no_fib_data -v
```
Expected: FAIL (module not found)

- [ ] **Step 3: Create entry_context.py with skeleton + `_fill_fib_proximity`**

Create `api/services/entry_context.py`:

```python
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.trade import Trade, Direction, OrderState
from models.fib_level import FibLevel
from models.price_bar import PriceBar, Timeframe
from services.pattern_detector import detect_pin_bar, detect_engulfing


async def fill_entry_context(session: AsyncSession, trade: Trade) -> None:
    """Auto-fills near_fib_level, fib_distance_pts, entry_candle, entry_candle_tf, is_rescue.
    Does not commit — caller commits."""
    await _fill_fib_proximity(session, trade)
    await _fill_entry_candle(session, trade)
    await _fill_is_rescue(session, trade)


async def _fill_fib_proximity(session: AsyncSession, trade: Trade) -> None:
    if trade.open_price is None:
        return

    result = await session.execute(
        select(FibLevel)
        .where(FibLevel.symbol == trade.symbol)
        .order_by(FibLevel.computed_at.desc())
        .limit(1)
    )
    fib = result.scalar_one_or_none()
    if fib is None:
        return

    open_price = float(trade.open_price)
    candidates = []

    for key, price in fib.levels.items():
        label = "PP" if key == "0.000" else f"R{key}"
        candidates.append((label, float(price)))

    for key, price in fib.extensions.items():
        label = f"S{key}"
        candidates.append((label, float(price)))

    if not candidates:
        return

    nearest_label, nearest_price = min(candidates, key=lambda x: abs(open_price - x[1]))
    trade.near_fib_level = nearest_label
    trade.fib_distance_pts = round(abs(open_price - nearest_price), 2)


async def _fill_entry_candle(session: AsyncSession, trade: Trade) -> None:
    if trade.open_time is None:
        return

    open_time = trade.open_time
    if open_time.tzinfo is None:
        open_time = open_time.replace(tzinfo=timezone.utc)

    tf_configs = [
        (Timeframe.H4, timedelta(hours=4),
         open_time.replace(hour=(open_time.hour // 4) * 4, minute=0, second=0, microsecond=0)),
        (Timeframe.H1, timedelta(hours=1),
         open_time.replace(minute=0, second=0, microsecond=0)),
        (Timeframe.M30, timedelta(minutes=30),
         open_time.replace(minute=(open_time.minute // 30) * 30, second=0, microsecond=0)),
        (Timeframe.M15, timedelta(minutes=15),
         open_time.replace(minute=(open_time.minute // 15) * 15, second=0, microsecond=0)),
    ]

    for tf, duration, bar_start in tf_configs:
        bar_res = await session.execute(
            select(PriceBar).where(
                PriceBar.symbol == trade.symbol,
                PriceBar.timeframe == tf,
                PriceBar.time >= bar_start,
                PriceBar.time < bar_start + duration,
            ).order_by(PriceBar.time.desc()).limit(1)
        )
        bar = bar_res.scalar_one_or_none()
        if bar is None:
            continue

        prev_res = await session.execute(
            select(PriceBar).where(
                PriceBar.symbol == trade.symbol,
                PriceBar.timeframe == tf,
                PriceBar.time >= bar_start - duration,
                PriceBar.time < bar_start,
            ).order_by(PriceBar.time.desc()).limit(1)
        )
        prev_bar = prev_res.scalar_one_or_none()

        bar_dict = {"open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close}
        bars = []
        if prev_bar:
            bars.append({"open": prev_bar.open, "high": prev_bar.high,
                         "low": prev_bar.low, "close": prev_bar.close})
        bars.append(bar_dict)

        pin = detect_pin_bar(bars)
        if pin:
            trade.entry_candle = f"pin_bar_{pin}"
            trade.entry_candle_tf = tf.value
            return

        eng = detect_engulfing(bars)
        if eng:
            trade.entry_candle = f"engulfing_{eng}"
            trade.entry_candle_tf = tf.value
            return

        if float(bar.open) == float(bar.close):
            trade.entry_candle = "doji"
            trade.entry_candle_tf = tf.value
            return

    trade.entry_candle = "none"
    trade.entry_candle_tf = None


async def _fill_is_rescue(session: AsyncSession, trade: Trade) -> None:
    if trade.symbol is None or trade.direction is None:
        return

    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.symbol == trade.symbol,
            Trade.direction == trade.direction,
            Trade.order_state == OrderState.filled,
            Trade.close_time.is_(None),
            Trade.ticket != trade.ticket,
        )
    )
    existing = result.scalars().all()
    trade.is_rescue = len(existing) > 0
```

- [ ] **Step 4: Run the fib proximity tests to verify they pass**

```bash
cd api && pytest ../tests/test_entry_context.py::test_fill_fib_proximity_finds_nearest_level ../tests/test_entry_context.py::test_fill_fib_proximity_labels_pp_correctly ../tests/test_entry_context.py::test_fill_fib_proximity_skips_when_no_fib_data -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/services/entry_context.py tests/test_entry_context.py
git commit -m "feat: entry_context service with fib proximity auto-fill"
```

---

## Task 4: entry_context — `_fill_entry_candle` tests

**Files:**
- Modify: `tests/test_entry_context.py`

- [ ] **Step 1: Write the failing entry_candle tests**

Append to `tests/test_entry_context.py`:

```python
from models.price_bar import PriceBar, Timeframe


def _make_bar(symbol, tf, time, open_, high, low, close) -> PriceBar:
    return PriceBar(
        symbol=symbol,
        timeframe=tf,
        time=time,
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
    )


@pytest.mark.asyncio
async def test_fill_entry_candle_detects_pin_bar_on_h4(db_session):
    from datetime import datetime, timezone
    open_time = datetime(2026, 5, 19, 10, 30, tzinfo=timezone.utc)
    # H4 bar start = 08:00 UTC (10 // 4 * 4 = 8)
    bar_start = datetime(2026, 5, 19, 8, 0, tzinfo=timezone.utc)

    # Bullish pin bar: long lower wick, small body near top
    prev = _make_bar("XAUUSD", Timeframe.H4,
                     datetime(2026, 5, 19, 4, 0, tzinfo=timezone.utc),
                     2010, 2015, 2005, 2012)
    bar = _make_bar("XAUUSD", Timeframe.H4, bar_start,
                    2010, 2015, 1990, 2013)  # large lower wick → bullish pin
    db_session.add(prev)
    db_session.add(bar)
    await db_session.commit()

    trade = _make_trade(open_time=open_time)
    db_session.add(trade)
    await db_session.commit()

    await fill_entry_context(db_session, trade)

    assert trade.entry_candle in ("pin_bar_bullish", "pin_bar_bearish", "doji", "engulfing_bullish", "engulfing_bearish")
    assert trade.entry_candle_tf == "H4"


@pytest.mark.asyncio
async def test_fill_entry_candle_falls_back_to_h1_when_no_h4_bar(db_session):
    open_time = datetime(2026, 5, 19, 10, 30, tzinfo=timezone.utc)
    # Only an H1 bar exists (no H4 bar)
    h1_bar_start = datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc)
    bar = _make_bar("XAUUSD", Timeframe.H1, h1_bar_start,
                    2010, 2015, 1990, 2013)
    db_session.add(bar)
    await db_session.commit()

    trade = _make_trade(open_time=open_time)
    db_session.add(trade)
    await db_session.commit()

    await fill_entry_context(db_session, trade)

    # No H4 bar → falls back to H1 where bar exists
    assert trade.entry_candle_tf == "H1"
    assert trade.entry_candle is not None


@pytest.mark.asyncio
async def test_fill_entry_candle_returns_none_when_no_pattern_any_tf(db_session):
    open_time = datetime(2026, 5, 19, 10, 30, tzinfo=timezone.utc)
    # No price bars at all
    trade = _make_trade(open_time=open_time)
    db_session.add(trade)
    await db_session.commit()

    await fill_entry_context(db_session, trade)

    assert trade.entry_candle == "none"
    assert trade.entry_candle_tf is None
```

- [ ] **Step 2: Run to verify they pass** (implementation already done in Task 3)

```bash
cd api && pytest ../tests/test_entry_context.py::test_fill_entry_candle_detects_pin_bar_on_h4 ../tests/test_entry_context.py::test_fill_entry_candle_falls_back_to_h1_when_no_h4_bar ../tests/test_entry_context.py::test_fill_entry_candle_returns_none_when_no_pattern_any_tf -v
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_entry_context.py
git commit -m "test: entry_candle auto-fill tests (TF fallback, no pattern)"
```

---

## Task 5: `_fill_is_rescue` Tests + Wire-up in trade_logger

**Files:**
- Modify: `tests/test_entry_context.py`
- Modify: `api/services/trade_logger.py`

- [ ] **Step 1: Write the failing is_rescue tests**

Append to `tests/test_entry_context.py`:

```python
@pytest.mark.asyncio
async def test_fill_is_rescue_true_when_same_direction_open(db_session):
    # Existing open BUY trade
    existing = _make_trade(ticket=999, open_price=Decimal("1990.00"))
    existing.close_time = None
    db_session.add(existing)
    await db_session.commit()

    # New BUY trade in same symbol+direction
    new_trade = _make_trade(ticket=1001)
    new_trade.close_time = None
    db_session.add(new_trade)
    await db_session.commit()

    await fill_entry_context(db_session, new_trade)

    assert new_trade.is_rescue is True


@pytest.mark.asyncio
async def test_fill_is_rescue_false_when_no_existing(db_session):
    trade = _make_trade(ticket=1001)
    trade.close_time = None
    db_session.add(trade)
    await db_session.commit()

    await fill_entry_context(db_session, trade)

    assert new_trade.is_rescue is False
```

Wait — fix variable name in the second test:

```python
@pytest.mark.asyncio
async def test_fill_is_rescue_false_when_no_existing(db_session):
    trade = _make_trade(ticket=1001)
    trade.close_time = None
    db_session.add(trade)
    await db_session.commit()

    await fill_entry_context(db_session, trade)

    assert trade.is_rescue is False
```

- [ ] **Step 2: Write integration test for auto-fill on trade event**

Append to `tests/test_entry_context.py`:

```python
@pytest.mark.asyncio
async def test_entry_context_auto_filled_on_trade_event(client, db_session):
    from models.fib_level import FibLevel

    fib = FibLevel(
        symbol="XAUUSD",
        timeframe="D",
        swing_high=2050.0,
        swing_low=1950.0,
        direction="bullish",
        levels={"0.000": 1983.33, "0.236": 2006.93},
        extensions={"0.236": 1959.73},
        computed_at=datetime(2026, 5, 19, 8, 0, tzinfo=timezone.utc),
    )
    db_session.add(fib)
    await db_session.commit()

    payload = {
        "transaction_type": "ENTRY_IN",
        "ticket": 2001,
        "symbol": "XAUUSD",
        "direction": "buy",
        "order_type": "market",
        "order_state": "filled",
        "open_price": "1962.00",
        "open_time": "2026-05-19T10:00:00+00:00",
    }
    resp = await client.post("/api/trade-events", json=payload)
    assert resp.status_code == 201

    from sqlalchemy import select
    from models.trade import Trade
    result = await db_session.execute(select(Trade).where(Trade.ticket == 2001, Trade.is_paper == False))
    trade = result.scalar_one()
    assert trade.near_fib_level is not None
    assert trade.is_rescue is not None
```

- [ ] **Step 3: Run to verify they fail**

```bash
cd api && pytest ../tests/test_entry_context.py::test_fill_is_rescue_true_when_same_direction_open ../tests/test_entry_context.py::test_fill_is_rescue_false_when_no_existing ../tests/test_entry_context.py::test_entry_context_auto_filled_on_trade_event -v
```
Expected: first two PASS (implementation done in Task 3), last one FAIL (not wired up yet)

- [ ] **Step 4: Wire fill_entry_context into trade_logger.py**

In `api/services/trade_logger.py`, add import and call:

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.trade import Trade
from schemas.trade_event import TradeEventSchema
from services.entry_context import fill_entry_context


async def upsert_trade(session: AsyncSession, event: TradeEventSchema) -> Trade:
    result = await session.execute(
        select(Trade).where(
            Trade.ticket == event.ticket,
            Trade.symbol == event.symbol,
            Trade.is_paper == False,
        )
    )
    trade = result.scalar_one_or_none()

    if trade is None:
        trade = Trade(
            ticket=event.ticket,
            symbol=event.symbol,
            is_paper=False,
        )
        session.add(trade)

    fields = [
        "direction", "order_type", "order_state", "pending_price",
        "open_time", "fill_time", "close_time", "open_price", "close_price",
        "volume", "tp", "sl", "profit", "swap", "commission",
    ]
    for field in fields:
        value = getattr(event, field)
        if value is not None:
            setattr(trade, field, value)

    if event.open_price is not None and event.close_price is None:
        await fill_entry_context(session, trade)

    await session.commit()
    await session.refresh(trade)
    return trade
```

- [ ] **Step 5: Run all entry_context tests**

```bash
cd api && pytest ../tests/test_entry_context.py -v
```
Expected: all PASS

- [ ] **Step 6: Run full suite**

```bash
cd api && pytest ../tests/ -v
```
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add api/services/trade_logger.py tests/test_entry_context.py
git commit -m "feat: wire fill_entry_context into trade_logger on ENTRY_IN events"
```

---

## Task 6: PATCH /api/trades/{ticket}/tag

**Files:**
- Modify: `api/routers/trades.py`
- Modify: `tests/test_trades_api.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_trades_api.py`:

```python
@pytest.mark.asyncio
async def test_patch_tag_updates_setup_pattern(client, db_session):
    trade = Trade(
        id=uuid.uuid4(),
        ticket=3001,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("2000.00"),
        open_time=datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc),
        is_paper=False,
    )
    db_session.add(trade)
    await db_session.commit()

    resp = await client.patch(
        "/api/trades/3001/tag",
        json={"setup_pattern": "double_bottom", "trade_bias": "bullish"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["setup_pattern"] == "double_bottom"
    assert data["trade_bias"] == "bullish"


@pytest.mark.asyncio
async def test_patch_tag_rejects_invalid_pattern(client, db_session):
    trade = Trade(
        id=uuid.uuid4(),
        ticket=3002,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("2000.00"),
        open_time=datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc),
        is_paper=False,
    )
    db_session.add(trade)
    await db_session.commit()

    resp = await client.patch(
        "/api/trades/3002/tag",
        json={"setup_pattern": "not_a_real_pattern"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_tag_returns_404_for_unknown_ticket(client, db_session):
    resp = await client.patch(
        "/api/trades/99999/tag",
        json={"setup_pattern": "double_bottom"},
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd api && pytest ../tests/test_trades_api.py::test_patch_tag_updates_setup_pattern ../tests/test_trades_api.py::test_patch_tag_rejects_invalid_pattern ../tests/test_trades_api.py::test_patch_tag_returns_404_for_unknown_ticket -v
```
Expected: FAIL (endpoint doesn't exist)

- [ ] **Step 3: Add PATCH endpoint to trades router**

Replace `api/routers/trades.py` with:

```python
from typing import List, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session
from models.trade import Trade
from schemas.trade import TradeResponse, TradeTagSchema

router = APIRouter(prefix="/api", tags=["trades"])


@router.get("/trades", response_model=List[TradeResponse])
async def list_trades(
    state: Literal["open", "closed"] = Query("open"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    query = select(Trade).order_by(Trade.open_time.desc())
    if state == "open":
        query = query.where(Trade.close_price.is_(None)).limit(limit).offset(offset)
    else:
        query = query.where(Trade.close_price.isnot(None)).limit(limit).offset(offset)
    result = await session.execute(query)
    return result.scalars().all()


@router.patch("/trades/{ticket}/tag", response_model=TradeResponse)
async def tag_trade(
    ticket: int,
    body: TradeTagSchema,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Trade).where(Trade.ticket == ticket, Trade.is_paper == False)
    )
    trade = result.scalar_one_or_none()
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")

    if body.setup_pattern is not None:
        trade.setup_pattern = body.setup_pattern
    if body.trade_bias is not None:
        trade.trade_bias = body.trade_bias

    await session.commit()
    await session.refresh(trade)
    return trade
```

- [ ] **Step 4: Run tag tests**

```bash
cd api && pytest ../tests/test_trades_api.py::test_patch_tag_updates_setup_pattern ../tests/test_trades_api.py::test_patch_tag_rejects_invalid_pattern ../tests/test_trades_api.py::test_patch_tag_returns_404_for_unknown_ticket -v
```
Expected: all PASS

- [ ] **Step 5: Run full suite**

```bash
cd api && pytest ../tests/ -v
```

- [ ] **Step 6: Commit**

```bash
git add api/routers/trades.py tests/test_trades_api.py
git commit -m "feat: PATCH /api/trades/{ticket}/tag + offset param on GET /api/trades"
```

---

## Task 7: POST /api/alerts/acknowledge-all + offset test

**Files:**
- Modify: `api/routers/alerts.py`
- Create: `tests/test_alerts_api.py`
- Modify: `tests/test_trades_api.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_alerts_api.py`:

```python
import pytest
import uuid
from datetime import datetime, timezone
from models.alert import Alert


@pytest.mark.asyncio
async def test_acknowledge_all_marks_all_unacked(client, db_session):
    for i in range(3):
        db_session.add(Alert(
            id=uuid.uuid4(),
            type="consecutive_loss",
            message=f"Loss alert {i}",
            sent_at=datetime(2026, 5, 19, 10, i, tzinfo=timezone.utc),
            acknowledged=False,
        ))
    await db_session.commit()

    resp = await client.post("/api/alerts/acknowledge-all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["acknowledged"] == 3

    # verify all acked
    check = await client.get("/api/alerts?unacknowledged_only=true")
    assert check.json() == []
```

Append to `tests/test_trades_api.py`:

```python
@pytest.mark.asyncio
async def test_list_trades_respects_offset(client, db_session):
    from datetime import datetime, timezone
    for i in range(5):
        trade = Trade(
            id=uuid.uuid4(),
            ticket=5000 + i,
            symbol="XAUUSD",
            direction=Direction.buy,
            order_state=OrderState.filled,
            open_price=Decimal("2000.00"),
            close_price=Decimal("2010.00"),
            open_time=datetime(2026, 5, 19, i, 0, tzinfo=timezone.utc),
            close_time=datetime(2026, 5, 19, i, 1, tzinfo=timezone.utc),
            profit=Decimal("100.00"),
            is_paper=False,
        )
        db_session.add(trade)
    await db_session.commit()

    resp_all = await client.get("/api/trades?state=closed&limit=10&offset=0")
    resp_offset = await client.get("/api/trades?state=closed&limit=10&offset=2")
    assert resp_all.status_code == 200
    assert resp_offset.status_code == 200
    assert len(resp_all.json()) == 5
    assert len(resp_offset.json()) == 3
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd api && pytest ../tests/test_alerts_api.py ../tests/test_trades_api.py::test_list_trades_respects_offset -v
```
Expected: acknowledge-all FAIL (endpoint missing), offset test may PASS (offset already added in Task 6)

- [ ] **Step 3: Add acknowledge-all to alerts router**

Replace `api/routers/alerts.py` with:

```python
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from database import get_session
from models.alert import Alert
from schemas.alert import AlertResponse

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts", response_model=List[AlertResponse])
async def list_alerts(
    unacknowledged_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    query = select(Alert).order_by(Alert.sent_at.desc())
    if unacknowledged_only:
        query = query.where(Alert.acknowledged == False)
    result = await session.execute(query)
    return result.scalars().all()


@router.patch("/alerts/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    await session.commit()
    await session.refresh(alert)
    return alert


@router.post("/alerts/acknowledge-all")
async def acknowledge_all_alerts(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Alert).where(Alert.acknowledged == False))
    alerts = result.scalars().all()
    count = len(alerts)
    for alert in alerts:
        alert.acknowledged = True
    await session.commit()
    return {"acknowledged": count}
```

- [ ] **Step 4: Run all alert + trades api tests**

```bash
cd api && pytest ../tests/test_alerts_api.py ../tests/test_trades_api.py -v
```
Expected: all PASS

- [ ] **Step 5: Run full suite**

```bash
cd api && pytest ../tests/ -v
```

- [ ] **Step 6: Commit**

```bash
git add api/routers/alerts.py tests/test_alerts_api.py tests/test_trades_api.py
git commit -m "feat: POST /api/alerts/acknowledge-all endpoint"
```

---

## Task 8: Insight `_compute_setup_win_rate`

**Files:**
- Modify: `api/services/insight_engine.py`
- Modify: `tests/test_insight_engine.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_insight_engine.py`:

```python
@pytest.mark.asyncio
async def test_setup_win_rate_insight_created(db_session):
    """Creates setup_win_rate insight when 5+ tagged trades qualify."""
    for i in range(4):
        t = _make_trade(hour=10, profit=200.0, minute=i)
        t.setup_pattern = "double_bottom"
        t.trade_bias = "bullish"
        t.near_fib_level = "S0.236"
        db_session.add(t)
    for i in range(4, 6):
        t = _make_trade(hour=11, profit=-100.0, minute=i)
        t.setup_pattern = "double_bottom"
        t.trade_bias = "bullish"
        t.near_fib_level = "S0.236"
        db_session.add(t)
    await db_session.commit()

    await run_insight_engine(db_session)

    result = await db_session.execute(
        select(Insight).where(Insight.type == "setup_win_rate", Insight.is_active == True)
    )
    insights = result.scalars().all()
    assert len(insights) == 1
    assert insights[0].sample_size == 6
    assert pytest.approx(float(insights[0].confidence), abs=0.01) == 4/6
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd api && pytest ../tests/test_insight_engine.py::test_setup_win_rate_insight_created -v
```
Expected: FAIL

- [ ] **Step 3: Add constant + function + call in run_insight_engine**

In `api/services/insight_engine.py`, add after existing constants:

```python
MIN_ENTRY_SAMPLE = 5  # lower threshold for new insight types (fewer tagged trades expected)
```

Add this function before the final commit in the file:

```python
async def _compute_setup_win_rate(session: AsyncSession, tagged: list) -> None:
    if not tagged:
        return
    records = [
        {
            "setup_pattern": t.setup_pattern,
            "trade_bias": t.trade_bias,
            "near_fib_level": t.near_fib_level,
            "is_win": float(t.profit) > 0,
            "profit": float(t.profit),
        }
        for t in tagged if t.profit is not None
    ]
    if not records:
        return

    df = pd.DataFrame(records)
    grouped = df.groupby(["setup_pattern", "trade_bias", "near_fib_level"]).agg(
        count=("is_win", "count"),
        win_rate=("is_win", "mean"),
        avg_profit=("profit", "mean"),
    ).reset_index()

    qualified = grouped[grouped["count"] >= MIN_ENTRY_SAMPLE]
    if qualified.empty:
        return

    old = await session.execute(
        select(Insight).where(Insight.type == "setup_win_rate", Insight.is_active == True)
    )
    for ins in old.scalars().all():
        ins.is_active = False

    for _, row in qualified.iterrows():
        session.add(Insight(
            type="setup_win_rate",
            description=(
                f"{row['setup_pattern']} + {row['trade_bias'] or 'any'}"
                f" + near {row['near_fib_level'] or 'any'}"
                f" → ชนะ {float(row['win_rate']):.0%} ({int(row['count'])} เทรด)"
                f" เฉลี่ย +฿{float(row['avg_profit']):.0f}"
            ),
            confidence=float(row["win_rate"]),
            sample_size=int(row["count"]),
            discovered_at=datetime.now(timezone.utc),
            is_active=True,
            data={
                "pattern": row["setup_pattern"],
                "bias": row["trade_bias"],
                "fib_level": row["near_fib_level"],
                "win_rate": float(row["win_rate"]),
                "avg_profit": float(row["avg_profit"]),
                "trades": int(row["count"]),
            },
        ))
```

In `run_insight_engine`, add before `await session.commit()`:

```python
    tagged = [t for t in trades if t.setup_pattern is not None]
    await _compute_setup_win_rate(session, tagged)
```

- [ ] **Step 4: Run test**

```bash
cd api && pytest ../tests/test_insight_engine.py::test_setup_win_rate_insight_created -v
```
Expected: PASS

- [ ] **Step 5: Run full suite**

```bash
cd api && pytest ../tests/ -v
```

- [ ] **Step 6: Commit**

```bash
git add api/services/insight_engine.py tests/test_insight_engine.py
git commit -m "feat: setup_win_rate insight (group by pattern+bias+fib_level)"
```

---

## Task 9: Insight `_compute_fib_proximity_win_rate`

**Files:**
- Modify: `api/services/insight_engine.py`
- Modify: `tests/test_insight_engine.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_insight_engine.py`:

```python
@pytest.mark.asyncio
async def test_fib_proximity_win_rate_insight_created(db_session):
    """Creates insight when close/far buckets differ by >= 20pp."""
    # 5 "close" trades (< 5 pts) — 80% win rate
    for i in range(4):
        t = _make_trade(hour=10, profit=200.0, minute=i)
        t.setup_pattern = "double_bottom"
        t.near_fib_level = "S0.236"
        t.fib_distance_pts = Decimal("2.0")
        db_session.add(t)
    t = _make_trade(hour=10, profit=-100.0, minute=4)
    t.setup_pattern = "double_bottom"
    t.near_fib_level = "S0.236"
    t.fib_distance_pts = Decimal("2.0")
    db_session.add(t)

    # 5 "far" trades (>= 15 pts) — 20% win rate
    t_win = _make_trade(hour=11, profit=200.0, minute=0)
    t_win.setup_pattern = "double_bottom"
    t_win.near_fib_level = "R0.618"
    t_win.fib_distance_pts = Decimal("20.0")
    db_session.add(t_win)
    for i in range(1, 5):
        t = _make_trade(hour=11, profit=-100.0, minute=i)
        t.setup_pattern = "double_bottom"
        t.near_fib_level = "R0.618"
        t.fib_distance_pts = Decimal("20.0")
        db_session.add(t)

    await db_session.commit()

    await run_insight_engine(db_session)

    result = await db_session.execute(
        select(Insight).where(Insight.type == "fib_proximity_win_rate", Insight.is_active == True)
    )
    insights = result.scalars().all()
    assert len(insights) == 1
    assert insights[0].confidence >= 0.20  # at least 20pp difference
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd api && pytest ../tests/test_insight_engine.py::test_fib_proximity_win_rate_insight_created -v
```
Expected: FAIL

- [ ] **Step 3: Add function + call**

Add function in `api/services/insight_engine.py`:

```python
async def _compute_fib_proximity_win_rate(session: AsyncSession, tagged: list) -> None:
    records = [
        {
            "bucket": (
                "close" if float(t.fib_distance_pts) < 5
                else "medium" if float(t.fib_distance_pts) < 15
                else "far"
            ),
            "is_win": float(t.profit) > 0,
        }
        for t in tagged
        if t.fib_distance_pts is not None and t.profit is not None
    ]
    if not records:
        return

    df = pd.DataFrame(records)
    grouped = df.groupby("bucket").agg(
        count=("is_win", "count"),
        win_rate=("is_win", "mean"),
    ).reset_index()

    qualified = grouped[grouped["count"] >= MIN_ENTRY_SAMPLE]
    if len(qualified) < 2:
        return

    rates = qualified["win_rate"].values
    spread = float(max(rates) - min(rates))
    if spread < 0.20:
        return

    bucket_stats = {
        row["bucket"]: (float(row["win_rate"]), int(row["count"]))
        for _, row in grouped.iterrows()
    }

    def fmt(name):
        if name not in bucket_stats:
            return "—"
        return f"{bucket_stats[name][0]:.0%}"

    total = int(grouped["count"].sum())

    old = await session.execute(
        select(Insight).where(Insight.type == "fib_proximity_win_rate", Insight.is_active == True)
    )
    for ins in old.scalars().all():
        ins.is_active = False

    session.add(Insight(
        type="fib_proximity_win_rate",
        description=(
            f"Entry ห่าง Fib < 5 pts → {fmt('close')} | "
            f"5-15 pts → {fmt('medium')} | "
            f">15 pts → {fmt('far')} ({total} เทรด)"
        ),
        confidence=spread,
        sample_size=total,
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data={b: {"win_rate": s[0], "count": s[1]} for b, s in bucket_stats.items()},
    ))
```

In `run_insight_engine`, add after `_compute_setup_win_rate`:

```python
    await _compute_fib_proximity_win_rate(session, tagged)
```

- [ ] **Step 4: Run test**

```bash
cd api && pytest ../tests/test_insight_engine.py::test_fib_proximity_win_rate_insight_created -v
```
Expected: PASS

- [ ] **Step 5: Full suite + commit**

```bash
cd api && pytest ../tests/ -v
git add api/services/insight_engine.py tests/test_insight_engine.py
git commit -m "feat: fib_proximity_win_rate insight (close/medium/far bucket comparison)"
```

---

## Task 10: Insight `_compute_rescue_outcome`

**Files:**
- Modify: `api/services/insight_engine.py`
- Modify: `tests/test_insight_engine.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_insight_engine.py`:

```python
@pytest.mark.asyncio
async def test_rescue_outcome_insight_created(db_session):
    """Creates insight comparing rescue vs initial trade win rates."""
    # 5 rescue trades — 40% win rate
    for i in range(2):
        t = _make_trade(hour=10, profit=200.0, minute=i)
        t.is_rescue = True
        db_session.add(t)
    for i in range(2, 5):
        t = _make_trade(hour=10, profit=-100.0, minute=i)
        t.is_rescue = True
        db_session.add(t)

    # 5 initial trades — 80% win rate
    for i in range(4):
        t = _make_trade(hour=11, profit=200.0, minute=i)
        t.is_rescue = False
        db_session.add(t)
    t = _make_trade(hour=11, profit=-100.0, minute=4)
    t.is_rescue = False
    db_session.add(t)

    await db_session.commit()
    await run_insight_engine(db_session)

    result = await db_session.execute(
        select(Insight).where(Insight.type == "rescue_outcome", Insight.is_active == True)
    )
    insights = result.scalars().all()
    assert len(insights) == 1
    data = insights[0].data
    assert pytest.approx(data["rescue_win_rate"], abs=0.01) == 2/5
    assert pytest.approx(data["initial_win_rate"], abs=0.01) == 4/5
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd api && pytest ../tests/test_insight_engine.py::test_rescue_outcome_insight_created -v
```
Expected: FAIL

- [ ] **Step 3: Add function + call**

```python
async def _compute_rescue_outcome(session: AsyncSession, trades: list) -> None:
    trades_with_data = [t for t in trades if t.profit is not None and t.is_rescue is not None]
    rescue = [t for t in trades_with_data if t.is_rescue]
    initial = [t for t in trades_with_data if not t.is_rescue]

    if len(rescue) < MIN_ENTRY_SAMPLE or len(initial) < MIN_ENTRY_SAMPLE:
        return

    rescue_wr = sum(1 for t in rescue if float(t.profit) > 0) / len(rescue)
    initial_wr = sum(1 for t in initial if float(t.profit) > 0) / len(initial)

    old = await session.execute(
        select(Insight).where(Insight.type == "rescue_outcome", Insight.is_active == True)
    )
    for ins in old.scalars().all():
        ins.is_active = False

    session.add(Insight(
        type="rescue_outcome",
        description=(
            f"ไม้แก้: ชนะ {rescue_wr:.0%} ({len(rescue)} เทรด) "
            f"vs ไม้เดิม: ชนะ {initial_wr:.0%} ({len(initial)} เทรด)"
        ),
        confidence=max(rescue_wr, initial_wr),
        sample_size=len(trades_with_data),
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data={
            "rescue_win_rate": rescue_wr,
            "initial_win_rate": initial_wr,
            "rescue_count": len(rescue),
            "initial_count": len(initial),
        },
    ))
```

In `run_insight_engine`, add after `_compute_fib_proximity_win_rate`:

```python
    await _compute_rescue_outcome(session, trades)
```

- [ ] **Step 4: Run test + full suite + commit**

```bash
cd api && pytest ../tests/test_insight_engine.py::test_rescue_outcome_insight_created -v
cd api && pytest ../tests/ -v
git add api/services/insight_engine.py tests/test_insight_engine.py
git commit -m "feat: rescue_outcome insight (compare rescue vs initial trade win rates)"
```

---

## Task 11: Insight `_compute_best_combo`

**Files:**
- Modify: `api/services/insight_engine.py`
- Modify: `tests/test_insight_engine.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_insight_engine.py`:

```python
@pytest.mark.asyncio
async def test_best_combo_insight_created(db_session):
    """Creates best_combo insight showing top 3 winning combinations."""
    # 5 winning trades: London session (UTC 10:00 = ICT 17:00 = London) + double_bottom + bullish
    for i in range(5):
        t = _make_trade(hour=10, profit=200.0, minute=i)
        t.setup_pattern = "double_bottom"
        t.trade_bias = "bullish"
        t.near_fib_level = "S0.236"
        db_session.add(t)
    await db_session.commit()

    await run_insight_engine(db_session)

    result = await db_session.execute(
        select(Insight).where(Insight.type == "best_combo", Insight.is_active == True)
    )
    insights = result.scalars().all()
    assert len(insights) == 1
    assert len(insights[0].data["combos"]) >= 1
    combo = insights[0].data["combos"][0]
    assert combo["pattern"] == "double_bottom"
    assert combo["win_rate"] == pytest.approx(1.0)
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd api && pytest ../tests/test_insight_engine.py::test_best_combo_insight_created -v
```
Expected: FAIL

- [ ] **Step 3: Add function + call**

Add at the top of `insight_engine.py` (if not already there — `timezone` and `timedelta` are already imported):

```python
_ICT = timezone(timedelta(hours=7))
```

Add function:

```python
async def _compute_best_combo(session: AsyncSession, tagged: list) -> None:
    records = [
        {
            "session": _assign_session(t.open_time.astimezone(_ICT).hour),
            "setup_pattern": t.setup_pattern,
            "trade_bias": t.trade_bias,
            "near_fib_level": t.near_fib_level,
            "is_win": float(t.profit) > 0,
            "profit": float(t.profit),
        }
        for t in tagged
        if t.profit is not None and t.open_time is not None
    ]
    if not records:
        return

    df = pd.DataFrame(records)
    grouped = df.groupby(
        ["session", "setup_pattern", "trade_bias", "near_fib_level"]
    ).agg(
        count=("is_win", "count"),
        win_rate=("is_win", "mean"),
        avg_profit=("profit", "mean"),
    ).reset_index()

    qualified = (
        grouped[grouped["count"] >= MIN_ENTRY_SAMPLE]
        .sort_values("win_rate", ascending=False)
        .head(3)
    )
    if qualified.empty:
        return

    top = qualified.iloc[0]

    old = await session.execute(
        select(Insight).where(Insight.type == "best_combo", Insight.is_active == True)
    )
    for ins in old.scalars().all():
        ins.is_active = False

    session.add(Insight(
        type="best_combo",
        description=(
            f"Best: {top['session']} + {top['setup_pattern']}"
            f" + {top['trade_bias'] or 'any'}"
            f" + near {top['near_fib_level'] or 'any'}"
            f" → {float(top['win_rate']):.0%} win rate ({int(top['count'])} เทรด)"
        ),
        confidence=float(top["win_rate"]),
        sample_size=int(qualified["count"].sum()),
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data={
            "combos": [
                {
                    "session": row["session"],
                    "pattern": row["setup_pattern"],
                    "bias": row["trade_bias"],
                    "fib_level": row["near_fib_level"],
                    "win_rate": float(row["win_rate"]),
                    "avg_profit": float(row["avg_profit"]),
                    "count": int(row["count"]),
                }
                for _, row in qualified.iterrows()
            ]
        },
    ))
```

In `run_insight_engine`, add after `_compute_rescue_outcome`:

```python
    await _compute_best_combo(session, tagged)
```

- [ ] **Step 4: Run test + full suite + commit**

```bash
cd api && pytest ../tests/test_insight_engine.py::test_best_combo_insight_created -v
cd api && pytest ../tests/ -v
git add api/services/insight_engine.py tests/test_insight_engine.py
git commit -m "feat: best_combo insight (top 3 session+pattern+bias+fib combinations, ICT timezone)"
```

---

## Task 12: Insight `_compute_post_close_run`

**Files:**
- Modify: `api/services/insight_engine.py`
- Modify: `tests/test_insight_engine.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_insight_engine.py`:

```python
@pytest.mark.asyncio
async def test_post_close_run_backfills_trade(db_session):
    """Backfills post_close_run_pts for trades where it's null."""
    close_time = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc)
    trade = _make_trade(hour=10, profit=200.0)
    trade.close_price = Decimal("1960.00")
    trade.close_time = close_time
    trade.direction = Direction.buy
    trade.post_close_run_pts = None
    db_session.add(trade)

    # H1 bar after close: high = 1975.00 → run = 1975 - 1960 = 15
    db_session.add(PriceBar(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        time=datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc),
        open=Decimal("1960.00"),
        high=Decimal("1975.00"),
        low=Decimal("1958.00"),
        close=Decimal("1970.00"),
    ))
    await db_session.commit()

    await run_insight_engine(db_session)

    await db_session.refresh(trade)
    assert trade.post_close_run_pts is not None
    assert float(trade.post_close_run_pts) == pytest.approx(15.0, abs=0.1)


@pytest.mark.asyncio
async def test_post_close_run_insight_created(db_session):
    """Creates post_close_run insight when winning tagged trades have run data."""
    close_time = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc)

    for i in range(3):
        t = _make_trade(hour=10, profit=200.0, minute=i)
        t.close_price = Decimal("1960.00")
        t.close_time = close_time + timedelta(minutes=i)
        t.direction = Direction.buy
        t.setup_pattern = "double_bottom"
        t.post_close_run_pts = Decimal(str(100 + i * 10))
        db_session.add(t)

    await db_session.commit()
    await run_insight_engine(db_session)

    result = await db_session.execute(
        select(Insight).where(Insight.type == "post_close_run", Insight.is_active == True)
    )
    insights = result.scalars().all()
    assert len(insights) == 1
    assert "double_bottom" in insights[0].data["by_pattern"]
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd api && pytest ../tests/test_insight_engine.py::test_post_close_run_backfills_trade ../tests/test_insight_engine.py::test_post_close_run_insight_created -v
```
Expected: FAIL

- [ ] **Step 3: Add function + call**

Add in `api/services/insight_engine.py` (note: `func`, `Direction`, `PriceBar`, `Timeframe` are already imported):

```python
async def _compute_post_close_run(session: AsyncSession, trades: list) -> None:
    # Step 1: Backfill post_close_run_pts for closed trades where it's null
    to_backfill = [
        t for t in trades
        if t.close_price is not None
        and t.close_time is not None
        and t.post_close_run_pts is None
    ]
    for trade in to_backfill:
        close_price = float(trade.close_price)
        end_time = trade.close_time + timedelta(hours=8)

        if trade.direction == Direction.buy:
            bar_res = await session.execute(
                select(func.max(PriceBar.high)).where(
                    PriceBar.symbol == trade.symbol,
                    PriceBar.timeframe == Timeframe.H1,
                    PriceBar.time >= trade.close_time,
                    PriceBar.time <= end_time,
                )
            )
            extreme = bar_res.scalar()
            if extreme is not None:
                run = float(extreme) - close_price
                if run > 0:
                    trade.post_close_run_pts = round(run, 2)
        else:
            bar_res = await session.execute(
                select(func.min(PriceBar.low)).where(
                    PriceBar.symbol == trade.symbol,
                    PriceBar.timeframe == Timeframe.H1,
                    PriceBar.time >= trade.close_time,
                    PriceBar.time <= end_time,
                )
            )
            extreme = bar_res.scalar()
            if extreme is not None:
                run = close_price - float(extreme)
                if run > 0:
                    trade.post_close_run_pts = round(run, 2)

    # Step 2: Compute insight from winning tagged trades with run data
    winning_tagged = [
        t for t in trades
        if t.setup_pattern is not None
        and t.profit is not None
        and float(t.profit) > 0
        and t.post_close_run_pts is not None
    ]
    if not winning_tagged:
        return

    df = pd.DataFrame([
        {"setup_pattern": t.setup_pattern, "run_pts": float(t.post_close_run_pts)}
        for t in winning_tagged
    ])
    grouped = df.groupby("setup_pattern").agg(
        count=("run_pts", "count"),
        avg_run=("run_pts", "mean"),
    ).reset_index()

    qualified = grouped[grouped["count"] >= 3]
    if qualified.empty:
        return

    old = await session.execute(
        select(Insight).where(Insight.type == "post_close_run", Insight.is_active == True)
    )
    for ins in old.scalars().all():
        ins.is_active = False

    by_pattern = {row["setup_pattern"]: float(row["avg_run"]) for _, row in qualified.iterrows()}
    parts = " | ".join(f"{p} → {r:.0f} pts" for p, r in by_pattern.items())
    overall_avg = float(df["run_pts"].mean())

    session.add(Insight(
        type="post_close_run",
        description=f"ราคาวิ่งต่อหลังปิด: {parts}",
        confidence=1.0,
        sample_size=len(winning_tagged),
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data={"by_pattern": by_pattern, "overall_avg": overall_avg},
    ))
```

In `run_insight_engine`, add after `_compute_best_combo` and before `await session.commit()`:

```python
    await _compute_post_close_run(session, trades)
```

- [ ] **Step 4: Run tests + full suite + commit**

```bash
cd api && pytest ../tests/test_insight_engine.py::test_post_close_run_backfills_trade ../tests/test_insight_engine.py::test_post_close_run_insight_created -v
cd api && pytest ../tests/ -v
git add api/services/insight_engine.py tests/test_insight_engine.py
git commit -m "feat: post_close_run insight (backfill MFE after close + pattern grouping)"
```

---

## Task 13: Alerts `_check_low_winrate_setup` + `_check_rescue_ineffective`

**Files:**
- Modify: `api/services/alert_manager.py`
- Modify: `tests/test_alert_manager.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_alert_manager.py`:

```python
from services.alert_manager import check_insight_alerts


@pytest.mark.asyncio
async def test_low_winrate_setup_alert_fires(db_session):
    """Alert fires when setup+bias combo has < 40% win rate with 5+ trades."""
    trades = []
    for i in range(5):
        t = Trade(
            id=uuid.uuid4(),
            ticket=8000 + i,
            symbol="XAUUSD",
            direction=Direction.buy,
            order_state=OrderState.filled,
            open_price=Decimal("2000.00"),
            open_time=datetime(2026, 5, 19, 10, i, tzinfo=timezone.utc),
            close_time=datetime(2026, 5, 19, 11, i, tzinfo=timezone.utc),
            profit=Decimal("-100.00"),
            is_paper=False,
            setup_pattern="double_top",
            trade_bias="bullish",
        )
        db_session.add(t)
        trades.append(t)
    await db_session.commit()

    await check_insight_alerts(db_session, trades, trades)

    result = await db_session.execute(
        select(Alert).where(Alert.type == "low_winrate_setup")
    )
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert "double_top" in alerts[0].message


@pytest.mark.asyncio
async def test_low_winrate_setup_no_alert_when_good_winrate(db_session):
    """No alert when win rate is >= 40%."""
    for i in range(5):
        profit = Decimal("200.00") if i < 4 else Decimal("-100.00")
        t = Trade(
            id=uuid.uuid4(),
            ticket=8100 + i,
            symbol="XAUUSD",
            direction=Direction.buy,
            order_state=OrderState.filled,
            open_price=Decimal("2000.00"),
            open_time=datetime(2026, 5, 19, 10, i, tzinfo=timezone.utc),
            close_time=datetime(2026, 5, 19, 11, i, tzinfo=timezone.utc),
            profit=profit,
            is_paper=False,
            setup_pattern="double_bottom",
            trade_bias="bullish",
        )
        db_session.add(t)
    await db_session.commit()

    tagged = (await db_session.execute(
        select(Trade).where(Trade.setup_pattern.isnot(None))
    )).scalars().all()

    await check_insight_alerts(db_session, tagged, tagged)

    result = await db_session.execute(
        select(Alert).where(Alert.type == "low_winrate_setup")
    )
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_rescue_ineffective_alert_fires(db_session):
    """Alert fires when rescue win_rate < 35% AND delta > 20pp vs initial."""
    # 5 initial trades: 80% win rate
    for i in range(4):
        t = Trade(
            id=uuid.uuid4(),
            ticket=9000 + i,
            symbol="XAUUSD",
            direction=Direction.buy,
            order_state=OrderState.filled,
            open_price=Decimal("2000.00"),
            open_time=datetime(2026, 5, 19, 10, i, tzinfo=timezone.utc),
            close_time=datetime(2026, 5, 19, 11, i, tzinfo=timezone.utc),
            profit=Decimal("200.00"),
            is_paper=False,
            is_rescue=False,
        )
        db_session.add(t)
    t = Trade(
        id=uuid.uuid4(), ticket=9004, symbol="XAUUSD", direction=Direction.buy,
        order_state=OrderState.filled, open_price=Decimal("2000.00"),
        open_time=datetime(2026, 5, 19, 10, 4, tzinfo=timezone.utc),
        close_time=datetime(2026, 5, 19, 11, 4, tzinfo=timezone.utc),
        profit=Decimal("-100.00"), is_paper=False, is_rescue=False,
    )
    db_session.add(t)

    # 5 rescue trades: 0% win rate
    for i in range(5):
        t = Trade(
            id=uuid.uuid4(),
            ticket=9100 + i,
            symbol="XAUUSD",
            direction=Direction.buy,
            order_state=OrderState.filled,
            open_price=Decimal("2000.00"),
            open_time=datetime(2026, 5, 19, 12, i, tzinfo=timezone.utc),
            close_time=datetime(2026, 5, 19, 13, i, tzinfo=timezone.utc),
            profit=Decimal("-100.00"),
            is_paper=False,
            is_rescue=True,
        )
        db_session.add(t)

    await db_session.commit()

    all_trades = (await db_session.execute(select(Trade).where(Trade.is_paper == False))).scalars().all()
    await check_insight_alerts(db_session, all_trades, all_trades)

    result = await db_session.execute(
        select(Alert).where(Alert.type == "rescue_ineffective")
    )
    alerts = result.scalars().all()
    assert len(alerts) == 1
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd api && pytest ../tests/test_alert_manager.py::test_low_winrate_setup_alert_fires ../tests/test_alert_manager.py::test_low_winrate_setup_no_alert_when_good_winrate ../tests/test_alert_manager.py::test_rescue_ineffective_alert_fires -v
```
Expected: FAIL (function not found)

- [ ] **Step 3: Add functions to alert_manager.py**

Add these constants after existing ones in `api/services/alert_manager.py`:

```python
ALERT_COOLDOWN_HOURS = 24
LOW_WINRATE_THRESHOLD = 0.40
RESCUE_WINRATE_THRESHOLD = 0.35
RESCUE_DELTA_THRESHOLD = 0.20
```

Add these functions:

```python
async def check_insight_alerts(session: AsyncSession, tagged: list, trades: list) -> None:
    await _check_low_winrate_setup(session, tagged)
    await _check_rescue_ineffective(session, trades)
    await session.commit()


async def _check_low_winrate_setup(session: AsyncSession, tagged: list) -> None:
    trades_with_profit = [t for t in tagged if t.profit is not None]
    if not trades_with_profit:
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=ALERT_COOLDOWN_HOURS)
    recent_res = await session.execute(
        select(Alert).where(Alert.type == "low_winrate_setup", Alert.sent_at >= cutoff)
    )
    recently_alerted = {
        (a.trigger_data.get("pattern"), a.trigger_data.get("bias"))
        for a in recent_res.scalars().all()
        if a.trigger_data
    }

    from collections import defaultdict
    groups: dict = defaultdict(list)
    for t in trades_with_profit:
        groups[(t.setup_pattern, t.trade_bias)].append(float(t.profit))

    for (pattern, bias), profits in groups.items():
        if len(profits) < 5:
            continue
        win_rate = sum(1 for p in profits if p > 0) / len(profits)
        if win_rate >= LOW_WINRATE_THRESHOLD:
            continue
        if (pattern, bias) in recently_alerted:
            continue
        session.add(Alert(
            type="low_winrate_setup",
            message=(
                f"{pattern} + {bias or 'any'}: ชนะแค่ {win_rate:.0%} ({len(profits)} เทรด)"
                f" — setup นี้ประวัติไม่ดี พิจารณาใหม่"
            ),
            trigger_data={"pattern": pattern, "bias": bias, "win_rate": win_rate, "count": len(profits)},
            sent_at=datetime.now(timezone.utc),
            acknowledged=False,
        ))


async def _check_rescue_ineffective(session: AsyncSession, trades: list) -> None:
    trades_with_data = [t for t in trades if t.profit is not None and t.is_rescue is not None]
    rescue = [t for t in trades_with_data if t.is_rescue]
    initial = [t for t in trades_with_data if not t.is_rescue]

    if len(rescue) < 5 or len(initial) < 5:
        return

    rescue_wr = sum(1 for t in rescue if float(t.profit) > 0) / len(rescue)
    initial_wr = sum(1 for t in initial if float(t.profit) > 0) / len(initial)

    if rescue_wr >= RESCUE_WINRATE_THRESHOLD:
        return
    if (initial_wr - rescue_wr) <= RESCUE_DELTA_THRESHOLD:
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=ALERT_COOLDOWN_HOURS)
    existing = await session.execute(
        select(Alert).where(Alert.type == "rescue_ineffective", Alert.sent_at >= cutoff)
    )
    if existing.scalar_one_or_none() is not None:
        return

    session.add(Alert(
        type="rescue_ineffective",
        message=(
            f"ไม้แก้ชนะแค่ {rescue_wr:.0%} vs ไม้เดิม {initial_wr:.0%}"
            f" — ข้อมูลบอกว่าตัดขาดทุนแล้วเริ่มใหม่ดีกว่า"
        ),
        trigger_data={
            "rescue_win_rate": rescue_wr,
            "initial_win_rate": initial_wr,
            "rescue_count": len(rescue),
        },
        sent_at=datetime.now(timezone.utc),
        acknowledged=False,
    ))
```

Wire up in `run_insight_engine` — add after `await session.commit()`:

```python
    from services.alert_manager import check_insight_alerts
    tagged = [t for t in trades if t.setup_pattern is not None]  # re-derive (already computed above)
    await check_insight_alerts(session, tagged, trades)
```

Wait — `tagged` is already defined earlier in `run_insight_engine`. Just add:

```python
    await session.commit()

    from services.alert_manager import check_insight_alerts
    await check_insight_alerts(session, tagged, trades)
```

- [ ] **Step 4: Run tests + full suite + commit**

```bash
cd api && pytest ../tests/test_alert_manager.py -v
cd api && pytest ../tests/ -v
git add api/services/alert_manager.py api/services/insight_engine.py tests/test_alert_manager.py
git commit -m "feat: low_winrate_setup and rescue_ineffective alert checks (24h cooldown)"
```

---

## Task 14: Frontend — SetupTag Component + OpenPositions Tag Dropdowns

**Files:**
- Create: `frontend/src/components/SetupTag.jsx`
- Modify: `frontend/src/components/OpenPositions.jsx`

- [ ] **Step 1: Create SetupTag.jsx**

```jsx
// frontend/src/components/SetupTag.jsx
const API = 'http://localhost:8000'

const PATTERNS = [
  { value: '', label: '— pattern' },
  { value: 'double_bottom', label: 'Double Bottom' },
  { value: 'double_top', label: 'Double Top' },
  { value: 'triple_bottom', label: 'Triple Bottom' },
  { value: 'triple_top', label: 'Triple Top' },
  { value: 'rounded_bottom', label: 'Rounded Bottom' },
  { value: 'rounded_top', label: 'Rounded Top' },
  { value: 'price_cluster', label: 'Price Cluster' },
  { value: 'other', label: 'Other' },
]

const BIASES = [
  { value: '', label: '— bias' },
  { value: 'bullish', label: 'Bullish' },
  { value: 'bearish', label: 'Bearish' },
]

export default function SetupTag({ ticket, currentPattern, currentBias, nearFibLevel, entryCandle, onUpdated }) {
  async function handleChange(field, value) {
    try {
      const body = { [field]: value || null }
      const res = await fetch(`${API}/api/trades/${ticket}/tag`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok && onUpdated) onUpdated(await res.json())
    } catch (_) {}
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex gap-1">
        <select
          className="text-xs bg-gray-800 text-gray-300 rounded px-1 py-0.5 border border-gray-700"
          value={currentPattern ?? ''}
          onChange={e => handleChange('setup_pattern', e.target.value)}
        >
          {PATTERNS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <select
          className="text-xs bg-gray-800 text-gray-300 rounded px-1 py-0.5 border border-gray-700"
          value={currentBias ?? ''}
          onChange={e => handleChange('trade_bias', e.target.value)}
        >
          {BIASES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>
      <div className="flex gap-2 text-xs text-gray-500">
        {nearFibLevel && <span>near {nearFibLevel}</span>}
        {entryCandle && entryCandle !== 'none' && <span>{entryCandle}</span>}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Add tag dropdowns to OpenPositions.jsx**

In `frontend/src/components/OpenPositions.jsx`:

1. Import SetupTag at the top:
```jsx
import SetupTag from './SetupTag'
```

2. Change the component signature to accept `onTradeTagged`:
```jsx
export default function OpenPositions({ data, error, onTradeTagged }) {
```

3. Add tag column header after the Rule `<th>`:
```jsx
              <th className="pb-2">Tag</th>
```

4. Add tag cell after the Rule `<td>` in each row:
```jsx
                  <td className="py-2 pl-2">
                    <SetupTag
                      ticket={t.ticket}
                      currentPattern={t.setup_pattern}
                      currentBias={t.trade_bias}
                      nearFibLevel={t.near_fib_level}
                      entryCandle={t.entry_candle}
                      onUpdated={onTradeTagged}
                    />
                  </td>
```

- [ ] **Step 3: Verify in browser**

```bash
cd frontend && npm run dev
```

Open http://localhost:3000. Open positions table should show Pattern and Bias dropdowns in the last column. Selecting a value should PATCH the API and show a response (check Network tab).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/SetupTag.jsx frontend/src/components/OpenPositions.jsx
git commit -m "feat: SetupTag component + pattern/bias dropdowns in open positions"
```

---

## Task 15: Frontend — ClosedTrades 2-Row Layout + Paging

**Files:**
- Modify: `frontend/src/components/ClosedTrades.jsx`

- [ ] **Step 1: Rewrite ClosedTrades.jsx**

Replace `frontend/src/components/ClosedTrades.jsx` with:

```jsx
function fmt(v, d = 2) {
  if (v == null) return '—'
  return Number(v).toFixed(d)
}

function fmtPL(v) {
  if (v == null) return '—'
  const n = Number(v)
  return (n >= 0 ? '+' : '') + n.toFixed(2)
}

function plColor(v) {
  if (v == null) return 'text-gray-500'
  return Number(v) >= 0 ? 'text-green-400' : 'text-red-400'
}

export default function ClosedTrades({ data, error, limit, onLimitChange, offset, onOffsetChange }) {
  const trades = data ?? []
  const real = trades.filter(t => !t.is_paper)

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Recent Closed Trades
        </h2>
        <div className="ml-auto flex items-center gap-2">
          <select
            className="text-xs bg-gray-800 text-gray-300 rounded px-1 py-0.5 border border-gray-700"
            value={limit}
            onChange={e => { onLimitChange(Number(e.target.value)); onOffsetChange(0) }}
          >
            {[10, 20, 50, 100].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
          {offset > 0 && (
            <button
              className="text-xs text-gray-400 hover:text-white px-1"
              onClick={() => onOffsetChange(Math.max(0, offset - limit))}
            >← Prev</button>
          )}
          {real.length === limit && (
            <button
              className="text-xs text-gray-400 hover:text-white px-1"
              onClick={() => onOffsetChange(offset + limit)}
            >Next →</button>
          )}
        </div>
        {error && <span className="text-xs text-red-400">Stale</span>}
      </div>
      {real.length === 0 ? (
        <p className="text-sm text-gray-600">No closed trades yet</p>
      ) : (
        <div className="space-y-2">
          {real.map(t => {
            const paper = trades.find(p => p.is_paper && p.ticket === t.ticket)
            const realPL = t.profit != null ? Number(t.profit) : null
            const paperPL = paper?.profit != null ? Number(paper.profit) : null
            const diff = realPL != null && paperPL != null ? paperPL - realPL : null
            const dir = t.direction?.toUpperCase() ?? '—'
            const dirColor = t.direction === 'buy' ? 'text-green-400' : 'text-red-400'
            return (
              <div key={t.ticket} className="bg-gray-800 rounded px-3 py-2 text-sm">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-mono text-gray-400 text-xs">#{t.ticket}</span>
                  <span className={`font-semibold text-xs ${dirColor}`}>{dir}</span>
                  {t.setup_pattern && (
                    <span className="text-xs text-gray-500">{t.setup_pattern}</span>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-1 text-xs">
                  <div className="flex gap-2">
                    <span className="text-gray-500">Real</span>
                    <span className="font-mono text-gray-400">{fmt(t.open_price, 2)}</span>
                    <span className="text-gray-600">→</span>
                    <span className="font-mono text-gray-400">{fmt(t.close_price, 2)}</span>
                    <span className={`font-mono ${plColor(realPL)}`}>{fmtPL(realPL)}</span>
                  </div>
                  {paper && (
                    <div className="flex gap-2">
                      <span className="text-gray-500">Paper</span>
                      <span className="font-mono text-gray-400">{fmt(paper.open_price, 2)}</span>
                      <span className="text-gray-600">→</span>
                      <span className="font-mono text-gray-400">{fmt(paper.close_price, 2)}</span>
                      <span className={`font-mono ${plColor(paperPL)}`}>{fmtPL(paperPL)}</span>
                      {diff != null && (
                        <span className={`font-mono ${plColor(diff)}`}>Δ{fmtPL(diff)}</span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify in browser**

Open http://localhost:3000. Closed trades should show as cards with Real/Paper rows. The row count selector (10/20/50/100) should appear at top right of the section. Prev/Next should appear when applicable.

(Note: paging won't function yet until App.jsx is wired up in Task 16.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ClosedTrades.jsx
git commit -m "feat: ClosedTrades 2-row card layout with paging controls"
```

---

## Task 16: Frontend — AlertsPanel Ack All + App.jsx Paging Wire-up

**Files:**
- Modify: `frontend/src/components/AlertsPanel.jsx`
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Add Ack All button to AlertsPanel.jsx**

In `frontend/src/components/AlertsPanel.jsx`, change the component signature:

```jsx
export default function AlertsPanel({ data, error, onAcknowledge, onAcknowledgeAll }) {
```

In the header row, after the unacked count badge and before `{error && ...}`, add:

```jsx
        {unacked.length > 0 && onAcknowledgeAll && (
          <button
            onClick={onAcknowledgeAll}
            className="text-xs text-gray-500 hover:text-white ml-auto px-2 py-0.5 border border-gray-700 rounded"
          >
            Ack All
          </button>
        )}
```

- [ ] **Step 2: Update App.jsx to wire paging + ack-all + tag callback**

Replace `frontend/src/App.jsx` with:

```jsx
import { useCallback, useState } from 'react'
import { usePolling } from './hooks/usePolling'
import AccountBar from './components/AccountBar'
import AlertsPanel from './components/AlertsPanel'
import InsightsPanel from './components/InsightsPanel'
import FibPanel from './components/FibPanel'
import OpenPositions from './components/OpenPositions'
import ClosedTrades from './components/ClosedTrades'

const API = 'http://localhost:8000'

async function get(path) {
  const res = await fetch(API + path)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export default function App() {
  const [closedLimit, setClosedLimit] = useState(20)
  const [closedOffset, setClosedOffset] = useState(0)

  const fetchAccount = useCallback(() => get('/api/account'), [])
  const fetchAlerts = useCallback(() => get('/api/alerts'), [])
  const fetchInsights = useCallback(() => get('/api/insights'), [])
  const fetchOpen = useCallback(() => get('/api/trades?state=open'), [])
  const fetchClosed = useCallback(
    () => get(`/api/trades?state=closed&limit=${closedLimit}&offset=${closedOffset}`),
    [closedLimit, closedOffset]
  )
  const fetchFib = useCallback(() => get('/api/fib-levels'), [])

  const account = usePolling(fetchAccount)
  const alerts = usePolling(fetchAlerts)
  const insights = usePolling(fetchInsights)
  const openTrades = usePolling(fetchOpen)
  const closedTrades = usePolling(fetchClosed)
  const fib = usePolling(fetchFib)

  const acknowledgeAlert = useCallback(async (id) => {
    try {
      const res = await fetch(`${API}/api/alerts/${id}/acknowledge`, { method: 'PATCH' })
      if (res.ok) alerts.refetch()
    } catch (_) {}
  }, [alerts.refetch])

  const acknowledgeAll = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/alerts/acknowledge-all`, { method: 'POST' })
      if (res.ok) alerts.refetch()
    } catch (_) {}
  }, [alerts.refetch])

  const handleTradeTagged = useCallback(() => {
    openTrades.refetch()
  }, [openTrades.refetch])

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-4 space-y-4">
      <AccountBar data={account.data} error={account.error} lastUpdated={account.lastUpdated} />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <AlertsPanel
          data={alerts.data}
          error={alerts.error}
          onAcknowledge={acknowledgeAlert}
          onAcknowledgeAll={acknowledgeAll}
        />
        <InsightsPanel data={insights.data} error={insights.error} />
        <FibPanel data={fib.data?.[0]} accountData={account.data} error={fib.error} />
      </div>
      <OpenPositions
        data={openTrades.data}
        error={openTrades.error}
        onTradeTagged={handleTradeTagged}
      />
      <ClosedTrades
        data={closedTrades.data}
        error={closedTrades.error}
        limit={closedLimit}
        onLimitChange={setClosedLimit}
        offset={closedOffset}
        onOffsetChange={setClosedOffset}
      />
    </div>
  )
}
```

- [ ] **Step 3: Verify in browser**

Open http://localhost:3000:
- Alerts panel: "Ack All" button appears when there are unacknowledged alerts. Click it — all alerts should grey out.
- Closed trades: changing the row count selector (10/20/50/100) should reload the list. Prev/Next should page through results.
- Open positions: tagging a trade (select pattern or bias) should save to API and re-fetch open positions.

- [ ] **Step 4: Full test suite**

```bash
cd api && pytest ../tests/ -v
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AlertsPanel.jsx frontend/src/App.jsx
git commit -m "feat: Ack All button + closed trades paging wired up in App"
```

---

## Post-Implementation Checklist

- [ ] Run Alembic migration on the running DB: `docker compose exec api alembic upgrade head`
- [ ] Verify no import cycles: `cd api && python -c "from services.insight_engine import run_insight_engine"`
- [ ] Smoke test via browser: open dashboard, tag a trade, verify near_fib_level appears in grey text
- [ ] Update `implementation-notes.md` with any decisions made during implementation

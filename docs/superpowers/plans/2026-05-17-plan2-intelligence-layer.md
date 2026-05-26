# Phase 2 Intelligence Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add Insight Engine (behavioral pattern analysis with pandas), Mirror Paper Trader (parallel paper entry on every real entry), and Alert Manager (real-time risk warnings) to the Trade Signal Partner backend, plus read APIs that expose the results.

**Architecture:** Three new services plug into the existing FastAPI request lifecycle — no background workers. Insight Engine and Alert Manager are called from trade_events router after every upsert; Alert Manager equity check is called from price_tick router. Mirror Trader creates a shadow paper trade on each real DEAL_ADD entry. Two new read-only routers expose /api/insights and /api/alerts.

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy 2.0 async + pandas 2.2.3; new `insights` and `alerts` tables via Alembic migration 002.

---

## File Structure

**New files:**
- `api/models/insight.py` — Insight ORM model (sa.JSON for SQLite test compat)
- `api/models/alert.py` — Alert ORM model (sa.JSON for SQLite test compat)
- `api/schemas/insight.py` — InsightResponse Pydantic schema
- `api/schemas/alert.py` — AlertResponse Pydantic schema
- `api/alembic/versions/002_add_insights_alerts.py` — Alembic migration (JSONB for PostgreSQL)
- `api/services/insight_engine.py` — pandas-based pattern analysis
- `api/services/mirror_trader.py` — paper trade creation on real entry
- `api/services/alert_manager.py` — equity buffer + double-down + consecutive-loss alerts
- `api/routers/insights.py` — GET /api/insights
- `api/routers/alerts.py` — GET /api/alerts, PATCH /api/alerts/{id}/acknowledge
- `tests/test_insight_engine.py`
- `tests/test_mirror_trader.py`
- `tests/test_alert_manager.py`
- `tests/test_insights_api.py`
- `tests/test_alerts_api.py`

**Modified files:**
- `api/requirements.txt` — add pandas==2.2.3, aiosqlite==0.20.0
- `api/models/__init__.py` — add Insight, Alert imports
- `api/routers/trade_events.py` — call mirror_trader + alert_manager + insight_engine
- `api/routers/price_tick.py` — call check_equity_buffer
- `api/main.py` — include insights_router, alerts_router

---

### Task 1: Models, Schemas, and Migration

**Files:**
- Create: `api/models/insight.py`
- Create: `api/models/alert.py`
- Create: `api/schemas/insight.py`
- Create: `api/schemas/alert.py`
- Create: `api/alembic/versions/002_add_insights_alerts.py`
- Modify: `api/models/__init__.py`
- Modify: `api/requirements.txt`

- [x] **Step 1: Write failing model creation test**

```python
# tests/test_models_phase2.py
import pytest
import uuid
from datetime import datetime, timezone
from models.insight import Insight
from models.alert import Alert


@pytest.mark.asyncio
async def test_create_insight(db_session):
    insight = Insight(
        id=uuid.uuid4(),
        type="time_bias",
        description="74% losses after 21:00",
        confidence=0.74,
        sample_size=12,
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data={"hour": 21, "loss_rate": 0.74},
    )
    db_session.add(insight)
    await db_session.commit()
    await db_session.refresh(insight)
    assert insight.type == "time_bias"
    assert float(insight.confidence) == pytest.approx(0.74)


@pytest.mark.asyncio
async def test_create_alert(db_session):
    alert = Alert(
        id=uuid.uuid4(),
        type="equity_buffer",
        message="Free margin below required buffer",
        trigger_data={"free_margin": 500.0, "required": 1000.0},
        sent_at=datetime.now(timezone.utc),
        acknowledged=False,
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)
    assert alert.type == "equity_buffer"
    assert alert.acknowledged is False
```

- [x] **Step 2: Run test to verify it fails**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_models_phase2.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'models.insight'`

- [x] **Step 3: Create `api/models/insight.py`**

```python
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Float, Integer, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from database import Base


class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(50), index=True)
    description: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
```

- [x] **Step 4: Create `api/models/alert.py`**

```python
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(50), index=True)
    message: Mapped[str] = mapped_column(Text)
    trigger_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
```

- [x] **Step 5: Update `api/models/__init__.py`**

```python
from .trade import Trade
from .price_bar import PriceBar
from .account_snapshot import AccountSnapshot
from .insight import Insight
from .alert import Alert

__all__ = ["Trade", "PriceBar", "AccountSnapshot", "Insight", "Alert"]
```

- [x] **Step 6: Create `api/schemas/insight.py`**

```python
from datetime import datetime
from typing import Optional, Any, List
from uuid import UUID
from pydantic import BaseModel


class InsightResponse(BaseModel):
    id: UUID
    type: str
    description: str
    confidence: float
    sample_size: int
    discovered_at: datetime
    is_active: bool
    data: Optional[Any] = None

    model_config = {"from_attributes": True}
```

- [x] **Step 7: Create `api/schemas/alert.py`**

```python
from datetime import datetime
from typing import Optional, Any
from uuid import UUID
from pydantic import BaseModel


class AlertResponse(BaseModel):
    id: UUID
    type: str
    message: str
    trigger_data: Optional[Any] = None
    sent_at: datetime
    acknowledged: bool

    model_config = {"from_attributes": True}
```

- [x] **Step 8: Update `api/requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy[asyncio]==2.0.35
asyncpg==0.29.0
psycopg2-binary==2.9.9
alembic==1.13.3
pydantic==2.9.2
pydantic-settings==2.5.2
python-dotenv==1.0.1
pandas==2.2.3
aiosqlite==0.20.0
```

- [x] **Step 9: Install pandas in local venv for tests**

```bash
/Users/nick/.venv/bin/pip install pandas==2.2.3
```
Expected: Successfully installed pandas-2.2.3

- [x] **Step 10: Create `api/alembic/versions/002_add_insights_alerts.py`**

```python
"""add insights and alerts

Revision ID: 002
Revises: 001
Create Date: 2026-05-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_insights_type", "insights", ["type"])

    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("trigger_data", postgresql.JSONB(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_type", "alerts", ["type"])


def downgrade() -> None:
    op.drop_index("ix_alerts_type", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_insights_type", table_name="insights")
    op.drop_table("insights")
```

- [x] **Step 11: Run tests to verify they pass**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_models_phase2.py -v
```
Expected: PASS (2 tests)

- [x] **Step 12: Run full suite to check no regressions**

```bash
/Users/nick/.venv/bin/python -m pytest tests/ -v
```
Expected: All existing tests pass

- [x] **Step 13: Apply migration in Docker**

```bash
docker compose run --rm --no-deps api alembic -c alembic.ini upgrade head
```
Expected: `Running upgrade 001 -> 002`

- [x] **Step 14: Commit**

```bash
git add api/models/insight.py api/models/alert.py api/schemas/insight.py api/schemas/alert.py
git add api/models/__init__.py api/requirements.txt
git add api/alembic/versions/002_add_insights_alerts.py
git add tests/test_models_phase2.py
git commit -m "feat: add Insight and Alert models, schemas, and migration 002"
```

---

### Task 2: Insight Engine

**Files:**
- Create: `api/services/insight_engine.py`
- Create: `tests/test_insight_engine.py`

- [x] **Step 1: Write failing tests**

```python
# tests/test_insight_engine.py
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import select
from models.trade import Trade, Direction, OrderState
from models.insight import Insight
from services.insight_engine import run_insight_engine


def _make_trade(hour: int, profit: float, direction: str = "buy") -> Trade:
    t = datetime(2026, 5, 17, hour, 0, 0, tzinfo=timezone.utc)
    return Trade(
        id=uuid.uuid4(),
        ticket=int(t.timestamp()),
        symbol="XAUUSD",
        direction=Direction(direction),
        order_state=OrderState.filled,
        open_price=Decimal("1950.00"),
        close_price=Decimal("1955.00") if profit > 0 else Decimal("1945.00"),
        open_time=t,
        close_time=t + timedelta(hours=1),
        profit=Decimal(str(profit)),
        volume=Decimal("0.10"),
        is_paper=False,
    )


@pytest.mark.asyncio
async def test_no_insight_with_insufficient_trades(db_session):
    """No insight created when sample_size < 10."""
    for i in range(5):
        db_session.add(_make_trade(hour=21, profit=-100.0))
    await db_session.commit()

    await run_insight_engine(db_session)

    result = await db_session.execute(select(Insight))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_time_bias_insight_created(db_session):
    """time_bias insight created when hour has >=10 trades with >=60% loss rate."""
    # 8 losses, 2 wins at hour 21 → 80% loss rate
    for i in range(8):
        db_session.add(_make_trade(hour=21, profit=-150.0))
    for i in range(2):
        db_session.add(_make_trade(hour=21, profit=100.0))
    # pad other hours so session_bias doesn't fire (< 10 trades per session)
    await db_session.commit()

    await run_insight_engine(db_session)

    result = await db_session.execute(
        select(Insight).where(Insight.type == "time_bias")
    )
    insights = result.scalars().all()
    assert len(insights) == 1
    assert insights[0].confidence == pytest.approx(0.8)
    assert insights[0].sample_size == 10
    assert insights[0].is_active is True


@pytest.mark.asyncio
async def test_time_bias_deactivates_old_insight(db_session):
    """Re-running insight engine deactivates previous time_bias insight."""
    # First run: 8 losses at hour 21
    for i in range(8):
        db_session.add(_make_trade(hour=21, profit=-100.0))
    for i in range(2):
        db_session.add(_make_trade(hour=21, profit=100.0))
    await db_session.commit()
    await run_insight_engine(db_session)

    # Second run: same data
    await run_insight_engine(db_session)

    result = await db_session.execute(select(Insight).where(Insight.type == "time_bias"))
    insights = result.scalars().all()
    active = [i for i in insights if i.is_active]
    inactive = [i for i in insights if not i.is_active]
    assert len(active) == 1
    assert len(inactive) == 1


@pytest.mark.asyncio
async def test_session_bias_insight_created(db_session):
    """session_bias insight created when one session has >=60% win rate with >=10 trades."""
    # 8 wins, 2 losses during London (hour 9)
    for i in range(8):
        db_session.add(_make_trade(hour=9, profit=100.0))
    for i in range(2):
        db_session.add(_make_trade(hour=9, profit=-100.0))
    await db_session.commit()

    await run_insight_engine(db_session)

    result = await db_session.execute(
        select(Insight).where(Insight.type == "session_bias")
    )
    insights = result.scalars().all()
    assert len(insights) == 1
    assert insights[0].confidence == pytest.approx(0.8)
    assert "London" in insights[0].description


@pytest.mark.asyncio
async def test_skips_paper_trades(db_session):
    """Insight engine ignores paper trades."""
    for i in range(10):
        t = _make_trade(hour=21, profit=-100.0)
        t.is_paper = True
        db_session.add(t)
    await db_session.commit()

    await run_insight_engine(db_session)

    result = await db_session.execute(select(Insight))
    assert result.scalars().all() == []
```

- [x] **Step 2: Run tests to verify they fail**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_insight_engine.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'services.insight_engine'`

- [x] **Step 3: Create `api/services/insight_engine.py`**

```python
import json
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import pandas as pd

from models.trade import Trade, OrderState
from models.insight import Insight

MIN_SAMPLE_SIZE = 10
MIN_CONFIDENCE = 0.6

SESSION_RANGES = {
    "Asia":   (0, 7),
    "London": (7, 16),
    "NY":     (13, 22),
}


async def run_insight_engine(session: AsyncSession) -> None:
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.order_state == OrderState.filled,
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
    return "Asia"


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
```

- [x] **Step 4: Run tests to verify they pass**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_insight_engine.py -v
```
Expected: PASS (5 tests)

- [x] **Step 5: Run full suite**

```bash
/Users/nick/.venv/bin/python -m pytest tests/ -v
```
Expected: All tests pass

- [x] **Step 6: Commit**

```bash
git add api/services/insight_engine.py tests/test_insight_engine.py
git commit -m "feat: add Insight Engine with time_bias and session_bias analysis"
```

---

### Task 3: Mirror Paper Trader

**Files:**
- Create: `api/services/mirror_trader.py`
- Create: `tests/test_mirror_trader.py`

- [x] **Step 1: Write failing tests**

```python
# tests/test_mirror_trader.py
import pytest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from models.trade import Trade, Direction, OrderState, PaperMode
from services.mirror_trader import create_mirror_trade
from schemas.trade_event import TradeEventSchema


def _entry_event(ticket: int = 1001, direction: str = "buy") -> TradeEventSchema:
    return TradeEventSchema(
        transaction_type="DEAL_ADD",
        ticket=ticket,
        symbol="XAUUSD",
        direction=direction,
        order_type="market",
        order_state="filled",
        open_price=Decimal("1950.00"),
        volume=Decimal("0.10"),
        open_time=datetime.now(timezone.utc),
    )


def _exit_event(ticket: int = 1001) -> TradeEventSchema:
    return TradeEventSchema(
        transaction_type="DEAL_ADD",
        ticket=ticket,
        symbol="XAUUSD",
        direction="buy",
        order_type="market",
        order_state="filled",
        close_price=Decimal("1960.00"),
        close_time=datetime.now(timezone.utc),
        profit=Decimal("100.00"),
    )


@pytest.mark.asyncio
async def test_creates_mirror_trade_on_entry(db_session):
    event = _entry_event()
    await create_mirror_trade(db_session, event)
    await db_session.commit()

    result = await db_session.execute(
        select(Trade).where(Trade.is_paper == True)
    )
    papers = result.scalars().all()
    assert len(papers) == 1
    assert papers[0].ticket == 1001
    assert papers[0].paper_mode == PaperMode.mirror
    assert float(papers[0].open_price) == pytest.approx(1950.00)


@pytest.mark.asyncio
async def test_no_mirror_on_exit_event(db_session):
    event = _exit_event()
    await create_mirror_trade(db_session, event)
    await db_session.commit()

    result = await db_session.execute(select(Trade).where(Trade.is_paper == True))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_no_duplicate_mirror(db_session):
    event = _entry_event()
    await create_mirror_trade(db_session, event)
    await db_session.commit()
    await create_mirror_trade(db_session, event)
    await db_session.commit()

    result = await db_session.execute(select(Trade).where(Trade.is_paper == True))
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_mirror_tp_from_winning_trades(db_session):
    """Paper TP computed from avg winning trade TP offset."""
    # Seed a winning buy trade with TP 50 points above open
    win = Trade(
        id=uuid.uuid4(),
        ticket=999,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("1900.00"),
        close_price=Decimal("1950.00"),
        tp=Decimal("1950.00"),
        volume=Decimal("0.10"),
        profit=Decimal("500.00"),
        open_time=datetime.now(timezone.utc),
        close_time=datetime.now(timezone.utc),
        is_paper=False,
    )
    db_session.add(win)
    await db_session.commit()

    event = _entry_event(ticket=1001, direction="buy")
    await create_mirror_trade(db_session, event)
    await db_session.commit()

    result = await db_session.execute(select(Trade).where(Trade.is_paper == True))
    paper = result.scalars().first()
    # TP offset = 50, so paper TP = 1950 + 50 = 2000
    assert float(paper.tp) == pytest.approx(2000.00, abs=0.01)


@pytest.mark.asyncio
async def test_mirror_direction_sell(db_session):
    event = _entry_event(ticket=1002, direction="sell")
    await create_mirror_trade(db_session, event)
    await db_session.commit()

    result = await db_session.execute(select(Trade).where(Trade.is_paper == True))
    paper = result.scalars().first()
    assert paper.direction == Direction.sell
```

- [x] **Step 2: Run tests to verify they fail**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_mirror_trader.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'services.mirror_trader'`

- [x] **Step 3: Create `api/services/mirror_trader.py`**

```python
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.trade import Trade, OrderState, PaperMode
from schemas.trade_event import TradeEventSchema


async def create_mirror_trade(session: AsyncSession, event: TradeEventSchema) -> None:
    if event.order_state != OrderState.filled:
        return
    if event.close_price is not None:
        return  # exit event, not entry
    if event.open_price is None:
        return

    existing = await session.execute(
        select(Trade).where(
            Trade.ticket == event.ticket,
            Trade.symbol == event.symbol,
            Trade.is_paper == True,
            Trade.paper_mode == PaperMode.mirror,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    paper_tp = await _compute_paper_tp(session, event)
    paper_sl = await _compute_paper_sl(session, event)

    session.add(Trade(
        ticket=event.ticket,
        symbol=event.symbol,
        direction=event.direction,
        order_type=event.order_type,
        order_state=OrderState.filled,
        open_price=event.open_price,
        volume=event.volume,
        open_time=event.open_time or datetime.now(timezone.utc),
        tp=paper_tp,
        sl=paper_sl,
        is_paper=True,
        paper_mode=PaperMode.mirror,
    ))


async def _compute_paper_tp(session: AsyncSession, event: TradeEventSchema):
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.order_state == OrderState.filled,
            Trade.direction == event.direction,
            Trade.profit > 0,
            Trade.tp.isnot(None),
            Trade.open_price.isnot(None),
        )
    )
    wins = result.scalars().all()
    offsets = [
        abs(float(t.tp) - float(t.open_price))
        for t in wins
        if t.tp and t.open_price
    ]
    if not offsets:
        return None

    avg_offset = sum(offsets) / len(offsets)
    open_price = float(event.open_price)
    if event.direction and event.direction.value == "buy":
        return Decimal(str(round(open_price + avg_offset, 5)))
    return Decimal(str(round(open_price - avg_offset, 5)))


async def _compute_paper_sl(session: AsyncSession, event: TradeEventSchema):
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.order_state == OrderState.filled,
            Trade.direction == event.direction,
            Trade.profit < 0,
            Trade.close_price.isnot(None),
            Trade.open_price.isnot(None),
        )
    )
    losses = result.scalars().all()
    offsets = [
        abs(float(t.close_price) - float(t.open_price))
        for t in losses
        if t.close_price and t.open_price
    ]
    if not offsets:
        return None

    avg_offset = sum(offsets) / len(offsets)
    open_price = float(event.open_price)
    if event.direction and event.direction.value == "buy":
        return Decimal(str(round(open_price - avg_offset, 5)))
    return Decimal(str(round(open_price + avg_offset, 5)))
```

- [x] **Step 4: Run tests to verify they pass**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_mirror_trader.py -v
```
Expected: PASS (5 tests)

- [x] **Step 5: Run full suite**

```bash
/Users/nick/.venv/bin/python -m pytest tests/ -v
```
Expected: All tests pass

- [x] **Step 6: Commit**

```bash
git add api/services/mirror_trader.py tests/test_mirror_trader.py
git commit -m "feat: add Mirror Paper Trader that shadows real entries with stat-based TP/SL"
```

---

### Task 4: Alert Manager

**Files:**
- Create: `api/services/alert_manager.py`
- Create: `tests/test_alert_manager.py`

- [x] **Step 1: Write failing tests**

```python
# tests/test_alert_manager.py
import pytest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from models.trade import Trade, Direction, OrderState
from models.alert import Alert
from services.alert_manager import check_trade_alerts, check_equity_buffer
from schemas.trade_event import TradeEventSchema
from schemas.price_tick import PriceTickSchema, AccountStateSchema, OHLCVSchema


def _filled_buy(ticket: int, profit: float = None, close: bool = False) -> Trade:
    t = Trade(
        id=uuid.uuid4(),
        ticket=ticket,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("1950.00"),
        volume=Decimal("1.00"),
        open_time=datetime.now(timezone.utc),
        is_paper=False,
    )
    if close and profit is not None:
        t.close_price = Decimal("1940.00") if profit < 0 else Decimal("1960.00")
        t.close_time = datetime.now(timezone.utc)
        t.profit = Decimal(str(profit))
    return t


def _event(ticket: int, order_state: str = "filled", direction: str = "buy",
           profit: float = None, close_price: float = None) -> TradeEventSchema:
    return TradeEventSchema(
        transaction_type="DEAL_ADD",
        ticket=ticket,
        symbol="XAUUSD",
        direction=direction,
        order_type="market",
        order_state=order_state,
        open_price=Decimal("1950.00") if close_price is None else None,
        close_price=Decimal(str(close_price)) if close_price else None,
        close_time=datetime.now(timezone.utc) if close_price else None,
        profit=Decimal(str(profit)) if profit is not None else None,
        volume=Decimal("1.00"),
        open_time=datetime.now(timezone.utc) if close_price is None else None,
    )


def _tick(free_margin: float, total_volume: float = 0.0) -> PriceTickSchema:
    return PriceTickSchema(
        timestamp=datetime.now(timezone.utc),
        symbol="XAUUSD",
        account=AccountStateSchema(
            equity=Decimal("10500.00"),
            balance=Decimal("10000.00"),
            margin=Decimal("450.00"),
            free_margin=Decimal(str(free_margin)),
            floating_pl=Decimal("-500.00"),
        ),
        bars={
            "H1": OHLCVSchema(open=Decimal("1950"), high=Decimal("1955"),
                              low=Decimal("1945"), close=Decimal("1952"), volume=Decimal("1000")),
        },
    )


@pytest.mark.asyncio
async def test_double_down_alert_fires(db_session):
    """Alert when user adds to same-direction open position."""
    existing = _filled_buy(ticket=1000)
    db_session.add(existing)
    await db_session.commit()

    event = _event(ticket=1001, direction="buy")
    await check_trade_alerts(db_session, event)

    result = await db_session.execute(select(Alert).where(Alert.type == "double_down"))
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert "buy" in alerts[0].message


@pytest.mark.asyncio
async def test_no_double_down_alert_on_first_trade(db_session):
    """No alert when there are no existing open positions."""
    event = _event(ticket=1001, direction="buy")
    await check_trade_alerts(db_session, event)

    result = await db_session.execute(select(Alert).where(Alert.type == "double_down"))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_consecutive_loss_alert_fires(db_session):
    """Alert after 3 consecutive losses."""
    for i, ticket in enumerate([1001, 1002, 1003]):
        t = _filled_buy(ticket=ticket, profit=-100.0, close=True)
        db_session.add(t)
    await db_session.commit()

    # Close event for trade 1003 (already in DB)
    event = _event(ticket=1003, close_price=1940.0, profit=-100.0)
    await check_trade_alerts(db_session, event)

    result = await db_session.execute(select(Alert).where(Alert.type == "consecutive_loss"))
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert "3" in alerts[0].message


@pytest.mark.asyncio
async def test_no_consecutive_loss_alert_after_win(db_session):
    """No alert when streak is broken by a win."""
    for profit in [-100.0, 50.0, -100.0]:
        t = _filled_buy(ticket=len(profit.__class__.__name__) + int(abs(profit)), profit=profit, close=True)
        db_session.add(t)
    await db_session.commit()

    event = _event(ticket=9999, close_price=1940.0, profit=-100.0)
    await check_trade_alerts(db_session, event)

    result = await db_session.execute(select(Alert).where(Alert.type == "consecutive_loss"))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_equity_buffer_alert_fires(db_session):
    """Alert when free_margin below required buffer for open lots."""
    # 1 lot open: required = 1.0 * 10000 * 0.01 * 100 = 10000 USD
    open_trade = _filled_buy(ticket=1001)
    db_session.add(open_trade)
    await db_session.commit()

    tick = _tick(free_margin=5000.0)  # below 10000 required
    await check_equity_buffer(db_session, tick)

    result = await db_session.execute(select(Alert).where(Alert.type == "equity_buffer"))
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert "5000" in alerts[0].message


@pytest.mark.asyncio
async def test_equity_buffer_no_alert_when_sufficient(db_session):
    """No alert when free_margin exceeds required buffer."""
    open_trade = _filled_buy(ticket=1001)
    db_session.add(open_trade)
    await db_session.commit()

    tick = _tick(free_margin=15000.0)  # above 10000 required
    await check_equity_buffer(db_session, tick)

    result = await db_session.execute(select(Alert).where(Alert.type == "equity_buffer"))
    assert result.scalars().all() == []
```

- [x] **Step 2: Run tests to verify they fail**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_alert_manager.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'services.alert_manager'`

- [x] **Step 3: Create `api/services/alert_manager.py`**

```python
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.trade import Trade, OrderState
from models.alert import Alert
from schemas.trade_event import TradeEventSchema
from schemas.price_tick import PriceTickSchema

CONSECUTIVE_LOSS_THRESHOLD = 3
EQUITY_BUFFER_POINTS = 10000


async def check_trade_alerts(session: AsyncSession, event: TradeEventSchema) -> None:
    await _check_double_down(session, event)
    await _check_consecutive_loss(session, event)


async def check_equity_buffer(session: AsyncSession, tick: PriceTickSchema) -> None:
    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.order_state == OrderState.filled,
            Trade.close_time.is_(None),
            Trade.symbol == tick.symbol,
        )
    )
    open_trades = result.scalars().all()
    if not open_trades:
        return

    total_volume = sum(float(t.volume) for t in open_trades if t.volume)
    # XAUUSD: 1 lot = 100 oz; each $0.01 move = $1/lot; 10000 points * $1/lot
    required_usd = total_volume * EQUITY_BUFFER_POINTS
    free_margin = float(tick.account.free_margin)

    if free_margin >= required_usd:
        return

    session.add(Alert(
        type="equity_buffer",
        message=(
            f"Free margin ${free_margin:.2f} is below the required "
            f"${required_usd:.2f} buffer for {total_volume:.2f} lots open"
        ),
        trigger_data={
            "free_margin": free_margin,
            "required_buffer": required_usd,
            "total_volume": total_volume,
        },
        sent_at=datetime.now(timezone.utc),
        acknowledged=False,
    ))
    await session.commit()


async def _check_double_down(session: AsyncSession, event: TradeEventSchema) -> None:
    if event.order_state != OrderState.filled:
        return
    if event.close_price is not None:
        return
    if event.open_price is None or not event.direction:
        return

    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.symbol == event.symbol,
            Trade.direction == event.direction,
            Trade.order_state == OrderState.filled,
            Trade.close_time.is_(None),
            Trade.ticket != event.ticket,
        )
    )
    existing = result.scalars().all()
    if not existing:
        return

    existing_volume = sum(float(t.volume) for t in existing if t.volume)
    session.add(Alert(
        type="double_down",
        message=(
            f"Adding to existing {event.direction.value} position "
            f"({existing_volume:.2f} lots already open on {event.symbol})"
        ),
        trigger_data={
            "symbol": event.symbol,
            "direction": event.direction.value,
            "existing_volume": existing_volume,
            "new_ticket": event.ticket,
        },
        sent_at=datetime.now(timezone.utc),
        acknowledged=False,
    ))
    await session.commit()


async def _check_consecutive_loss(session: AsyncSession, event: TradeEventSchema) -> None:
    if event.profit is None or float(event.profit) >= 0:
        return

    result = await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.symbol == event.symbol,
            Trade.order_state == OrderState.filled,
            Trade.close_time.isnot(None),
            Trade.profit.isnot(None),
        ).order_by(Trade.close_time.desc()).limit(CONSECUTIVE_LOSS_THRESHOLD)
    )
    recent = result.scalars().all()

    if len(recent) < CONSECUTIVE_LOSS_THRESHOLD:
        return
    if not all(float(t.profit) < 0 for t in recent):
        return

    total_loss = sum(float(t.profit) for t in recent)
    session.add(Alert(
        type="consecutive_loss",
        message=(
            f"{CONSECUTIVE_LOSS_THRESHOLD} consecutive losses detected "
            f"(total: ${total_loss:.2f}). Consider stepping back."
        ),
        trigger_data={
            "count": CONSECUTIVE_LOSS_THRESHOLD,
            "total_loss": total_loss,
            "tickets": [t.ticket for t in recent],
        },
        sent_at=datetime.now(timezone.utc),
        acknowledged=False,
    ))
    await session.commit()
```

- [x] **Step 4: Run tests to verify they pass**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_alert_manager.py -v
```
Expected: PASS (6 tests)

- [x] **Step 5: Run full suite**

```bash
/Users/nick/.venv/bin/python -m pytest tests/ -v
```
Expected: All tests pass

- [x] **Step 6: Commit**

```bash
git add api/services/alert_manager.py tests/test_alert_manager.py
git commit -m "feat: add Alert Manager with equity_buffer, double_down, consecutive_loss alerts"
```

---

### Task 5: Read API Endpoints

**Files:**
- Create: `api/routers/insights.py`
- Create: `api/routers/alerts.py`
- Create: `tests/test_insights_api.py`
- Create: `tests/test_alerts_api.py`

- [x] **Step 1: Write failing tests**

```python
# tests/test_insights_api.py
import pytest
import uuid
from datetime import datetime, timezone
from models.insight import Insight


@pytest.mark.asyncio
async def test_get_insights_empty(client):
    response = await client.get("/api/insights")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_insights_returns_active_only(client, db_session):
    active = Insight(
        id=uuid.uuid4(),
        type="time_bias",
        description="80% loss at hour 21",
        confidence=0.8,
        sample_size=15,
        discovered_at=datetime.now(timezone.utc),
        is_active=True,
        data=None,
    )
    inactive = Insight(
        id=uuid.uuid4(),
        type="session_bias",
        description="Old insight",
        confidence=0.7,
        sample_size=12,
        discovered_at=datetime.now(timezone.utc),
        is_active=False,
        data=None,
    )
    db_session.add(active)
    db_session.add(inactive)
    await db_session.commit()

    response = await client.get("/api/insights")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["type"] == "time_bias"
    assert data[0]["confidence"] == pytest.approx(0.8)
```

```python
# tests/test_alerts_api.py
import pytest
import uuid
from datetime import datetime, timezone
from models.alert import Alert


@pytest.mark.asyncio
async def test_get_alerts_empty(client):
    response = await client.get("/api/alerts")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_alerts_returns_all(client, db_session):
    for i in range(2):
        db_session.add(Alert(
            id=uuid.uuid4(),
            type="double_down",
            message=f"Alert {i}",
            trigger_data={"index": i},
            sent_at=datetime.now(timezone.utc),
            acknowledged=False,
        ))
    await db_session.commit()

    response = await client.get("/api/alerts")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_get_alerts_unacknowledged_filter(client, db_session):
    for ack in [True, False]:
        db_session.add(Alert(
            id=uuid.uuid4(),
            type="equity_buffer",
            message="Alert",
            sent_at=datetime.now(timezone.utc),
            acknowledged=ack,
        ))
    await db_session.commit()

    response = await client.get("/api/alerts?unacknowledged_only=true")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["acknowledged"] is False


@pytest.mark.asyncio
async def test_acknowledge_alert(client, db_session):
    alert_id = uuid.uuid4()
    db_session.add(Alert(
        id=alert_id,
        type="double_down",
        message="Test alert",
        sent_at=datetime.now(timezone.utc),
        acknowledged=False,
    ))
    await db_session.commit()

    response = await client.patch(f"/api/alerts/{alert_id}/acknowledge")
    assert response.status_code == 200
    assert response.json()["acknowledged"] is True


@pytest.mark.asyncio
async def test_acknowledge_alert_not_found(client):
    fake_id = uuid.uuid4()
    response = await client.patch(f"/api/alerts/{fake_id}/acknowledge")
    assert response.status_code == 404
```

- [x] **Step 2: Run tests to verify they fail**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_insights_api.py tests/test_alerts_api.py -v
```
Expected: FAIL with 404 (routes not registered yet)

- [x] **Step 3: Create `api/routers/insights.py`**

```python
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session
from models.insight import Insight
from schemas.insight import InsightResponse

router = APIRouter(prefix="/api", tags=["insights"])


@router.get("/insights", response_model=List[InsightResponse])
async def list_insights(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Insight)
        .where(Insight.is_active == True)
        .order_by(Insight.discovered_at.desc())
    )
    return result.scalars().all()
```

- [x] **Step 4: Create `api/routers/alerts.py`**

```python
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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
```

- [x] **Step 5: Register routers in `api/main.py`**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from database import Base, engine
import models  # noqa: F401
from routers.trade_events import router as trade_events_router
from routers.price_tick import router as price_tick_router
from routers.insights import router as insights_router
from routers.alerts import router as alerts_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Trade Signal Partner", lifespan=lifespan)
app.include_router(trade_events_router)
app.include_router(price_tick_router)
app.include_router(insights_router)
app.include_router(alerts_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [x] **Step 6: Run tests to verify they pass**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_insights_api.py tests/test_alerts_api.py -v
```
Expected: PASS (7 tests)

- [x] **Step 7: Run full suite**

```bash
/Users/nick/.venv/bin/python -m pytest tests/ -v
```
Expected: All tests pass

- [x] **Step 8: Commit**

```bash
git add api/routers/insights.py api/routers/alerts.py api/main.py
git add tests/test_insights_api.py tests/test_alerts_api.py
git commit -m "feat: add /api/insights and /api/alerts read endpoints"
```

---

### Task 6: Wire Up Services into Existing Routers

**Files:**
- Modify: `api/routers/trade_events.py`
- Modify: `api/routers/price_tick.py`

- [x] **Step 1: Write failing integration tests**

```python
# tests/test_wire_up.py
import pytest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from models.trade import Trade
from models.alert import Alert


ENTRY_EVENT = {
    "transaction_type": "DEAL_ADD",
    "ticket": 5001,
    "symbol": "XAUUSD",
    "direction": "buy",
    "order_type": "market",
    "order_state": "filled",
    "open_price": 1950.00,
    "volume": 1.00,
    "open_time": "2026-05-17T10:00:00Z",
}

PRICE_TICK = {
    "timestamp": "2026-05-17T10:00:00Z",
    "symbol": "XAUUSD",
    "account": {
        "equity": 10000.0,
        "balance": 10000.0,
        "margin": 500.0,
        "free_margin": 500.0,   # intentionally low to trigger equity_buffer
        "floating_pl": 0.0,
    },
    "bars": {
        "H1": {"open": 1950, "high": 1955, "low": 1945, "close": 1952, "volume": 1000},
    },
}


@pytest.mark.asyncio
async def test_trade_event_creates_mirror_trade(client, db_session):
    response = await client.post("/api/trade-events", json=ENTRY_EVENT)
    assert response.status_code == 201

    result = await db_session.execute(select(Trade).where(Trade.is_paper == True))
    papers = result.scalars().all()
    assert len(papers) == 1
    assert papers[0].ticket == 5001


@pytest.mark.asyncio
async def test_price_tick_triggers_equity_buffer_alert(client, db_session):
    # Open a 1-lot position first
    await client.post("/api/trade-events", json=ENTRY_EVENT)

    # Price tick with insufficient free_margin (500 < 10000 required for 1 lot)
    response = await client.post("/api/price-tick", json=PRICE_TICK)
    assert response.status_code == 200

    result = await db_session.execute(select(Alert).where(Alert.type == "equity_buffer"))
    alerts = result.scalars().all()
    assert len(alerts) == 1


@pytest.mark.asyncio
async def test_double_down_alert_from_endpoint(client, db_session):
    # First entry
    await client.post("/api/trade-events", json=ENTRY_EVENT)

    # Second buy entry on same symbol
    second = {**ENTRY_EVENT, "ticket": 5002}
    await client.post("/api/trade-events", json=second)

    result = await db_session.execute(select(Alert).where(Alert.type == "double_down"))
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert "buy" in alerts[0].message
```

- [x] **Step 2: Run tests to verify they fail**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_wire_up.py -v
```
Expected: FAIL — mirror trade and alerts not created (services not wired yet)

- [x] **Step 3: Update `api/routers/trade_events.py`**

```python
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from schemas.trade_event import TradeEventSchema
from services.trade_logger import upsert_trade
from services.mirror_trader import create_mirror_trade
from services.alert_manager import check_trade_alerts
from services.insight_engine import run_insight_engine

router = APIRouter(prefix="/api", tags=["trade-events"])


@router.post("/trade-events", status_code=status.HTTP_201_CREATED)
async def receive_trade_event(
    event: TradeEventSchema,
    session: AsyncSession = Depends(get_session),
):
    trade = await upsert_trade(session, event)
    await create_mirror_trade(session, event)
    await check_trade_alerts(session, event)
    await run_insight_engine(session)
    return {"id": str(trade.id), "ticket": trade.ticket}
```

- [x] **Step 4: Update `api/routers/price_tick.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from schemas.price_tick import PriceTickSchema
from services.price_handler import save_price_tick
from services.alert_manager import check_equity_buffer

router = APIRouter(prefix="/api", tags=["price-tick"])


@router.post("/price-tick")
async def receive_price_tick(
    tick: PriceTickSchema,
    session: AsyncSession = Depends(get_session),
):
    await save_price_tick(session, tick)
    await check_equity_buffer(session, tick)
    return {"status": "saved", "timestamp": tick.timestamp.isoformat()}
```

- [x] **Step 5: Run integration tests to verify they pass**

```bash
/Users/nick/.venv/bin/python -m pytest tests/test_wire_up.py -v
```
Expected: PASS (3 tests)

- [x] **Step 6: Run full suite**

```bash
/Users/nick/.venv/bin/python -m pytest tests/ -v
```
Expected: All tests pass (22+ tests)

- [x] **Step 7: Rebuild Docker and verify stack**

```bash
docker compose up --build -d
docker compose logs -f api
```
Expected: API starts without errors, `POST /api/price-tick` returns 200

- [x] **Step 8: Commit**

```bash
git add api/routers/trade_events.py api/routers/price_tick.py tests/test_wire_up.py
git commit -m "feat: wire Insight Engine, Mirror Trader, and Alert Manager into request lifecycle"
```

---

## Summary of All Commands

| Purpose | Command |
|---------|---------|
| Run all tests | `/Users/nick/.venv/bin/python -m pytest tests/ -v` |
| Apply migration | `docker compose run --rm --no-deps api alembic -c alembic.ini upgrade head` |
| Rebuild stack | `docker compose up --build -d` |
| Tail API logs | `docker compose logs -f api` |
| Install pandas locally | `/Users/nick/.venv/bin/pip install pandas==2.2.3` |

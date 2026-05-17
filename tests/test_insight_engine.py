import pytest
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import select
from models.trade import Trade, Direction, OrderState
from models.insight import Insight
from services.insight_engine import run_insight_engine


def _make_trade(hour: int, profit: float, direction: str = "buy", minute: int = 0) -> Trade:
    t = datetime(2026, 5, 17, hour, minute, 0, tzinfo=timezone.utc)
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
        db_session.add(_make_trade(hour=21, profit=-100.0, minute=i))
    await db_session.commit()

    await run_insight_engine(db_session)

    result = await db_session.execute(select(Insight))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_time_bias_insight_created(db_session):
    """time_bias insight created when hour has >=10 trades with >=60% loss rate."""
    # 8 losses, 2 wins at hour 21 → 80% loss rate
    for i in range(8):
        db_session.add(_make_trade(hour=21, profit=-150.0, minute=i))
    for i in range(2):
        db_session.add(_make_trade(hour=21, profit=100.0, minute=i + 8))
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
        db_session.add(_make_trade(hour=21, profit=-100.0, minute=i))
    for i in range(2):
        db_session.add(_make_trade(hour=21, profit=100.0, minute=i + 8))
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
        db_session.add(_make_trade(hour=9, profit=100.0, minute=i))
    for i in range(2):
        db_session.add(_make_trade(hour=9, profit=-100.0, minute=i + 8))
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
        t = _make_trade(hour=21, profit=-100.0, minute=i)
        t.is_paper = True
        db_session.add(t)
    await db_session.commit()

    await run_insight_engine(db_session)

    result = await db_session.execute(select(Insight))
    assert result.scalars().all() == []

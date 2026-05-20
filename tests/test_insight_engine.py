import pytest
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import select
from models.trade import Trade, Direction, OrderState
from models.insight import Insight
from models.price_bar import PriceBar, Timeframe
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


# ── large_adverse_recovery ────────────────────────────────────────────────────

def _make_trade_with_adverse_bar(
    i: int, profit: float, open_price: float, min_low: float
) -> tuple[Trade, PriceBar]:
    t = datetime(2026, 5, 17, 10, 0, 0, tzinfo=timezone.utc) + timedelta(hours=i)
    close_p = open_price + 5.0 if profit > 0 else open_price - 5.0
    trade = Trade(
        id=uuid.uuid4(),
        ticket=90000 + i,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal(str(open_price)),
        close_price=Decimal(str(close_p)),
        open_time=t,
        close_time=t + timedelta(hours=1),
        profit=Decimal(str(profit)),
        volume=Decimal("0.10"),
        is_paper=False,
    )
    bar = PriceBar(
        time=t,
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        open=Decimal(str(open_price)),
        high=Decimal(str(open_price + 2)),
        low=Decimal(str(min_low)),
        close=Decimal(str(open_price - 1)),
        volume=Decimal("500"),
    )
    return trade, bar


@pytest.mark.asyncio
async def test_large_adverse_recovery_insight_created(db_session):
    """Insight created when 10+ trades had 200+ pt adverse move."""
    # 3 wins, 7 losses → 30% win rate when large adverse move occurred
    for i in range(3):
        t, b = _make_trade_with_adverse_bar(i, profit=50.0, open_price=2000.0, min_low=1790.0)
        db_session.add(t)
        db_session.add(b)
    for i in range(3, 10):
        t, b = _make_trade_with_adverse_bar(i, profit=-100.0, open_price=2000.0, min_low=1790.0)
        db_session.add(t)
        db_session.add(b)
    await db_session.commit()

    await run_insight_engine(db_session)

    result = await db_session.execute(
        select(Insight).where(Insight.type == "large_adverse_recovery")
    )
    insights = result.scalars().all()
    assert len(insights) == 1
    assert insights[0].sample_size == 10
    assert insights[0].data["win_rate"] == pytest.approx(0.3)
    assert insights[0].is_active is True


@pytest.mark.asyncio
async def test_large_adverse_recovery_no_insight_when_move_too_small(db_session):
    """No insight when price bar low is within threshold (< 200 pts adverse)."""
    for i in range(10):
        t, b = _make_trade_with_adverse_bar(i, profit=-100.0, open_price=2000.0, min_low=1850.0)
        db_session.add(t)
        db_session.add(b)
    await db_session.commit()

    await run_insight_engine(db_session)

    result = await db_session.execute(
        select(Insight).where(Insight.type == "large_adverse_recovery")
    )
    assert result.scalars().all() == []


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
        select(Insight).where(
            Insight.type == "setup_win_rate",
            Insight.is_active == True,
        )
    )
    insights = result.scalars().all()
    assert len(insights) == 1
    assert insights[0].sample_size == 6
    assert pytest.approx(float(insights[0].confidence), abs=0.01) == 4 / 6


@pytest.mark.asyncio
async def test_fib_proximity_win_rate_insight_created(db_session):
    """Creates insight when close/far buckets differ by >= 20pp."""
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
        select(Insight).where(
            Insight.type == "fib_proximity_win_rate",
            Insight.is_active == True,
        )
    )
    insights = result.scalars().all()
    assert len(insights) == 1
    assert insights[0].confidence >= 0.20


@pytest.mark.asyncio
async def test_rescue_outcome_insight_created(db_session):
    """Creates insight comparing rescue vs initial trade win rates."""
    # 5 rescue trades: 40% win rate
    for i in range(2):
        t = _make_trade(hour=10, profit=200.0, minute=i)
        t.is_rescue = True
        db_session.add(t)
    for i in range(2, 5):
        t = _make_trade(hour=10, profit=-100.0, minute=i)
        t.is_rescue = True
        db_session.add(t)

    # 5 initial trades: 80% win rate
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
        select(Insight).where(
            Insight.type == "rescue_outcome",
            Insight.is_active == True,
        )
    )
    insights = result.scalars().all()
    assert len(insights) == 1
    data = insights[0].data
    assert pytest.approx(data["rescue_win_rate"], abs=0.01) == 2 / 5
    assert pytest.approx(data["initial_win_rate"], abs=0.01) == 4 / 5


@pytest.mark.asyncio
async def test_best_combo_insight_created(db_session):
    """Creates best_combo insight showing top 3 winning combinations."""
    # UTC 10:00 = ICT 17:00 = NY by the existing session assignment.
    for i in range(5):
        t = _make_trade(hour=10, profit=200.0, minute=i)
        t.setup_pattern = "double_bottom"
        t.trade_bias = "bullish"
        t.near_fib_level = "S0.236"
        db_session.add(t)
    await db_session.commit()

    await run_insight_engine(db_session)

    result = await db_session.execute(
        select(Insight).where(
            Insight.type == "best_combo",
            Insight.is_active == True,
        )
    )
    insights = result.scalars().all()
    assert len(insights) == 1
    assert len(insights[0].data["combos"]) >= 1
    combo = insights[0].data["combos"][0]
    assert combo["pattern"] == "double_bottom"
    assert combo["win_rate"] == pytest.approx(1.0)


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

    # H1 bar after close: high = 1975.00, run = 1975 - 1960 = 15
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
        select(Insight).where(
            Insight.type == "post_close_run",
            Insight.is_active == True,
        )
    )
    insights = result.scalars().all()
    assert len(insights) == 1
    assert "double_bottom" in insights[0].data["by_pattern"]

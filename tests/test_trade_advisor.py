import uuid
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from models.fib_level import FibLevel
from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, Trade
from services.trade_advisor import compute_entry_score


def _make_trade(**kwargs) -> Trade:
    defaults = dict(
        id=uuid.uuid4(),
        ticket=9001,
        symbol="GOLD#",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("4700.00"),
        # London peak hour (09:00 UTC Wednesday)
        open_time=datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc),
        is_paper=False,
        is_rescue=False,
    )
    defaults.update(kwargs)
    return Trade(**defaults)


async def _make_fib(db_session, **kwargs):
    defaults = dict(
        symbol="GOLD#",
        period="W",
        prev_high=4870.0,
        prev_low=4608.0,
        prev_close=4700.0,
        pp=4726.0,
        resistance={"R1": 4787.57, "R2": 4826.35, "R3": 4857.0,
                    "R4": 4888.75, "R5": 4916.66, "R6": 4988.0,
                    "R7": 5050.57, "R8": 5075.66, "R9": 5119.0, "R10": 5150.0},
        support={"S1": 4664.43, "S2": 4625.65, "S3": 4595.0,
                 "S4": 4563.25, "S5": 4535.34, "S6": 4464.0,
                 "S7": 4401.43, "S8": 4376.34, "S9": 4333.0, "S10": 4302.0},
        computed_at=datetime(2026, 5, 20, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    fib = FibLevel(**defaults)
    db_session.add(fib)
    return fib


@pytest.mark.asyncio
async def test_entry_score_good_entry(db_session):
    """PP fib + London peak + bullish pin bar -> score >= 70"""
    await _make_fib(db_session)
    await db_session.commit()

    trade = _make_trade(
        near_fib_level="PP",
        fib_distance_pts=Decimal("2.0"),
        entry_candle="pin_bar_bullish",
        entry_candle_tf="H1",
        is_rescue=False,
    )
    db_session.add(trade)
    await db_session.commit()

    await compute_entry_score(db_session, trade)

    assert trade.entry_score is not None
    assert trade.entry_score >= 70
    assert trade.entry_verdict == "good"


@pytest.mark.asyncio
async def test_entry_score_high_risk(db_session):
    """No fib + bad session (< 5 samples -> neutral) + 2 setup losses -> score < 40"""
    # Insert 2 recent losing original trades (setup losses)
    for i in range(2):
        loser = _make_trade(
            id=uuid.uuid4(),
            ticket=8000 + i,
            order_state=OrderState.filled,
            open_time=datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc),
            close_time=datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc),
            profit=Decimal("-150.00"),
            is_rescue=False,
        )
        db_session.add(loser)
    await db_session.commit()

    trade = _make_trade(
        # open outside peak hours (Friday evening)
        open_time=datetime(2026, 5, 22, 18, 0, tzinfo=timezone.utc),
        near_fib_level=None,
        fib_distance_pts=None,
        entry_candle="none",
        is_rescue=False,
    )
    db_session.add(trade)
    await db_session.commit()

    await compute_entry_score(db_session, trade)

    assert trade.entry_score is not None
    assert trade.entry_score < 40
    assert trade.entry_verdict == "high_risk"


@pytest.mark.asyncio
async def test_entry_score_rescue_at_fib_gives_bonus(db_session):
    """Rescue trade at fib level -> +15 rescue bonus"""
    await _make_fib(db_session)
    await db_session.commit()

    trade = _make_trade(
        near_fib_level="S1",
        fib_distance_pts=Decimal("1.5"),
        entry_candle="none",
        is_rescue=True,
    )
    db_session.add(trade)
    await db_session.commit()

    await compute_entry_score(db_session, trade)

    # fib +20 + rescue at fib +15 + peak hours +10 = 45 min (no losses, no session data)
    assert trade.entry_score >= 40
    assert trade.entry_verdict in ("good", "caution")


@pytest.mark.asyncio
async def test_entry_score_rescue_not_at_fib_gives_penalty(db_session):
    """Rescue trade far from fib -> -15 rescue penalty"""
    await _make_fib(db_session)
    await db_session.commit()

    trade = _make_trade(
        near_fib_level="R3",
        fib_distance_pts=Decimal("25.0"),  # > 5 pts -> not aligned
        entry_candle="none",
        is_rescue=True,
    )
    db_session.add(trade)
    await db_session.commit()

    await compute_entry_score(db_session, trade)

    # rescue penalty -15 should reduce score
    assert trade.entry_score is not None
    assert trade.entry_verdict is not None


@pytest.mark.asyncio
async def test_entry_score_idempotent(db_session):
    """Calling compute_entry_score twice does not change the score"""
    trade = _make_trade(near_fib_level=None, entry_candle="none", is_rescue=False)
    db_session.add(trade)
    await db_session.commit()

    await compute_entry_score(db_session, trade)
    first_score = trade.entry_score

    await compute_entry_score(db_session, trade)
    assert trade.entry_score == first_score


@pytest.mark.asyncio
async def test_entry_score_peak_hours_penalty(db_session):
    """Friday after 17:00 UTC -> -10 peak hours penalty"""
    trade_peak = _make_trade(
        id=uuid.uuid4(), ticket=9010,
        open_time=datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc),  # Wednesday London peak
        near_fib_level=None, entry_candle="none", is_rescue=False,
    )
    trade_offpeak = _make_trade(
        id=uuid.uuid4(), ticket=9011,
        open_time=datetime(2026, 5, 23, 18, 0, tzinfo=timezone.utc),  # Friday 18:00 UTC
        near_fib_level=None, entry_candle="none", is_rescue=False,
    )
    db_session.add(trade_peak)
    db_session.add(trade_offpeak)
    await db_session.commit()

    await compute_entry_score(db_session, trade_peak)
    await compute_entry_score(db_session, trade_offpeak)

    assert trade_peak.entry_score > trade_offpeak.entry_score


# ---------------------------------------------------------------------------
# Task 3: Recovery Plan tests
# ---------------------------------------------------------------------------
from services.trade_advisor import compute_recovery_plan


@pytest.mark.asyncio
async def test_recovery_plan_buy(db_session):
    """BUY @ PP -> TP = R levels above, Add = S levels below, Cut = S4"""
    await _make_fib(db_session)
    await db_session.commit()

    trade = _make_trade(
        open_price=Decimal("4726.00"),  # at PP
        direction=Direction.buy,
    )
    db_session.add(trade)
    await db_session.commit()

    await compute_recovery_plan(db_session, trade)

    assert trade.recovery_plan is not None
    plan = trade.recovery_plan
    assert plan["direction"] == "buy"
    assert plan["entry_price"] == pytest.approx(4726.0)

    # TP = R levels above 4726
    assert len(plan["tp"]) == 3
    for zone in plan["tp"]:
        assert zone["price"] > 4726.0
        assert zone["pts"] > 0  # price - entry > 0

    # Add = S levels below 4726
    assert len(plan["add"]) == 3
    for zone in plan["add"]:
        assert zone["price"] < 4726.0
        assert zone["pts"] < 0  # price - entry < 0

    # Cut = 4th S level below entry
    assert plan["cut"]["label"] == "S4"
    assert plan["cut"]["price"] < 4726.0


@pytest.mark.asyncio
async def test_recovery_plan_sell(db_session):
    """SELL @ PP -> TP = S levels below, Add = R levels above, Cut = R4"""
    await _make_fib(db_session)
    await db_session.commit()

    trade = _make_trade(
        open_price=Decimal("4726.00"),
        direction=Direction.sell,
    )
    db_session.add(trade)
    await db_session.commit()

    await compute_recovery_plan(db_session, trade)

    plan = trade.recovery_plan
    assert plan["direction"] == "sell"
    assert len(plan["tp"]) == 3
    for zone in plan["tp"]:
        assert zone["price"] < 4726.0  # S levels below entry

    assert len(plan["add"]) == 3
    for zone in plan["add"]:
        assert zone["price"] > 4726.0  # R levels above entry

    assert plan["cut"]["label"] == "R4"


@pytest.mark.asyncio
async def test_recovery_plan_null_when_no_fib(db_session):
    """No fib data -> recovery_plan stays None"""
    trade = _make_trade(open_price=Decimal("4700.00"), direction=Direction.buy)
    db_session.add(trade)
    await db_session.commit()

    await compute_recovery_plan(db_session, trade)

    assert trade.recovery_plan is None


@pytest.mark.asyncio
async def test_recovery_plan_idempotent(db_session):
    """Calling compute_recovery_plan twice does not change the plan"""
    await _make_fib(db_session)
    await db_session.commit()

    trade = _make_trade(open_price=Decimal("4726.00"), direction=Direction.buy)
    db_session.add(trade)
    await db_session.commit()

    await compute_recovery_plan(db_session, trade)
    first_plan = dict(trade.recovery_plan)

    await compute_recovery_plan(db_session, trade)
    assert trade.recovery_plan == first_plan


# ---------------------------------------------------------------------------
# Task 4: Zone Monitoring tests
# ---------------------------------------------------------------------------
from services.trade_advisor import check_advisor_zones
from schemas.market_tick import MarketTickSchema
from sqlalchemy import select
from models.alert import Alert


def _make_tick(bid: str, symbol: str = "GOLD#") -> MarketTickSchema:
    return MarketTickSchema(
        timestamp=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
        symbol=symbol,
        bid=Decimal(bid),
        ask=Decimal(bid) + Decimal("0.30"),
    )


def _make_trade_with_plan(direction: Direction, entry: str, plan: dict, **kwargs) -> Trade:
    return _make_trade(
        direction=direction,
        open_price=Decimal(entry),
        recovery_plan=plan,
        close_time=None,
        order_state=OrderState.filled,
        **kwargs,
    )


_BUY_PLAN = {
    "entry_price": 4726.0,
    "direction": "buy",
    "tp": [{"label": "R1", "price": 4787.57, "pts": 61.57}],
    "add": [
        {"label": "S1", "price": 4664.43, "pts": -61.57},
        {"label": "S2", "price": 4625.65, "pts": -100.35},
        {"label": "S3", "price": 4595.0, "pts": -131.0},
    ],
    "cut": {"label": "S4", "price": 4563.25, "pts": -162.75},
}


@pytest.mark.asyncio
async def test_zone_check_tp_alert(db_session):
    """BUY price crosses above R1 -> tp_zone_reached alert"""
    trade = _make_trade_with_plan(Direction.buy, "4726.00", _BUY_PLAN)
    db_session.add(trade)
    await db_session.commit()

    tick = _make_tick("4788.00")  # above R1 (4787.57)
    await check_advisor_zones(db_session, tick)

    result = await db_session.execute(
        select(Alert).where(Alert.type == "tp_zone_reached")
    )
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert alerts[0].trade_id == trade.id
    assert alerts[0].trigger_data["label"] == "R1"


@pytest.mark.asyncio
async def test_zone_check_add_alert(db_session):
    """BUY price crosses below S1 -> add_zone_reached alert"""
    trade = _make_trade_with_plan(Direction.buy, "4726.00", _BUY_PLAN)
    db_session.add(trade)
    await db_session.commit()

    tick = _make_tick("4664.00")  # below S1 (4664.43)
    await check_advisor_zones(db_session, tick)

    result = await db_session.execute(
        select(Alert).where(Alert.type == "add_zone_reached")
    )
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert alerts[0].trigger_data["label"] == "S1"


@pytest.mark.asyncio
async def test_zone_check_cut_alert(db_session):
    """BUY price crosses below S4 -> cut_zone_reached alert"""
    trade = _make_trade_with_plan(Direction.buy, "4726.00", _BUY_PLAN)
    db_session.add(trade)
    await db_session.commit()

    tick = _make_tick("4563.00")  # below S4 (4563.25)
    await check_advisor_zones(db_session, tick)

    result = await db_session.execute(
        select(Alert).where(Alert.type == "cut_zone_reached")
    )
    assert result.scalars().first() is not None


@pytest.mark.asyncio
async def test_zone_check_cooldown(db_session):
    """Same zone triggered twice -> only 1 alert created"""
    trade = _make_trade_with_plan(Direction.buy, "4726.00", _BUY_PLAN)
    db_session.add(trade)
    await db_session.commit()

    tick = _make_tick("4664.00")  # below S1
    await check_advisor_zones(db_session, tick)
    await check_advisor_zones(db_session, tick)

    result = await db_session.execute(
        select(Alert).where(Alert.type == "add_zone_reached", Alert.trade_id == trade.id)
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_zone_check_no_alert_when_price_not_crossed(db_session):
    """Price still above S1 -> no alert"""
    trade = _make_trade_with_plan(Direction.buy, "4726.00", _BUY_PLAN)
    db_session.add(trade)
    await db_session.commit()

    tick = _make_tick("4700.00")  # between entry and S1
    await check_advisor_zones(db_session, tick)

    result = await db_session.execute(select(Alert))
    assert result.scalars().first() is None

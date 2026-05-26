import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from models.pattern import PaperTraderRule
from models.trade import Direction, OrderState, PaperMode, Trade
from schemas.market_tick import MarketTickSchema
from services.paper_exit_manager import close_paper_trades_on_tick


def _paper_trade(
    direction: Direction,
    open_price: str,
    tp: Optional[str],
    sl: Optional[str],
    ticket: int = 7001,
) -> Trade:
    return Trade(
        id=uuid.uuid4(),
        ticket=ticket,
        symbol="XAUUSD",
        direction=direction,
        order_state=OrderState.filled,
        open_price=Decimal(open_price),
        volume=Decimal("0.10"),
        tp=Decimal(tp) if tp else None,
        sl=Decimal(sl) if sl else None,
        open_time=datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
        is_paper=True,
        paper_mode=PaperMode.independent,
    )


def _tick(bid: str, ask: str) -> MarketTickSchema:
    return MarketTickSchema(
        timestamp=datetime(2026, 5, 18, 10, 5, tzinfo=timezone.utc),
        symbol="XAUUSD",
        bid=Decimal(bid),
        ask=Decimal(ask),
    )


@pytest.mark.asyncio
async def test_closes_buy_paper_trade_at_tp(db_session):
    db_session.add(_paper_trade(Direction.buy, "1950.00", "1960.00", "1945.00"))
    await db_session.commit()

    closed = await close_paper_trades_on_tick(db_session, _tick("1960.10", "1960.30"))

    assert closed == 1
    trade = (await db_session.execute(select(Trade))).scalars().first()
    assert trade.close_price == Decimal("1960.00")
    assert trade.close_time.replace(tzinfo=timezone.utc) == datetime(
        2026, 5, 18, 10, 5, tzinfo=timezone.utc
    )
    assert trade.profit == Decimal("100.00")
    assert trade.paper_exit_reason == "tp"


@pytest.mark.asyncio
async def test_closes_buy_paper_trade_at_sl(db_session):
    trade = _paper_trade(Direction.buy, "1950.00", "1960.00", "1945.00")
    db_session.add(trade)
    await db_session.commit()

    closed = await close_paper_trades_on_tick(db_session, _tick("1944.90", "1945.10"))

    assert closed == 1
    assert trade.close_price == Decimal("1945.00")
    assert trade.profit == Decimal("-50.00")
    assert trade.paper_exit_reason == "sl"


@pytest.mark.asyncio
async def test_closes_sell_paper_trade_at_tp(db_session):
    trade = _paper_trade(Direction.sell, "1950.00", "1940.00", "1955.00")
    db_session.add(trade)
    await db_session.commit()

    closed = await close_paper_trades_on_tick(db_session, _tick("1939.80", "1939.95"))

    assert closed == 1
    assert trade.close_price == Decimal("1940.00")
    assert trade.profit == Decimal("100.00")


@pytest.mark.asyncio
async def test_closes_sell_paper_trade_at_sl(db_session):
    trade = _paper_trade(Direction.sell, "1950.00", "1940.00", "1955.00")
    db_session.add(trade)
    await db_session.commit()

    closed = await close_paper_trades_on_tick(db_session, _tick("1954.80", "1955.10"))

    assert closed == 1
    assert trade.close_price == Decimal("1955.00")
    assert trade.profit == Decimal("-50.00")


@pytest.mark.asyncio
async def test_ignores_real_and_already_closed_trades(db_session):
    real = _paper_trade(Direction.buy, "1950.00", "1960.00", "1945.00", ticket=7001)
    real.is_paper = False
    closed = _paper_trade(Direction.buy, "1950.00", "1960.00", "1945.00", ticket=7002)
    closed.close_price = Decimal("1960.00")
    closed.close_time = datetime(2026, 5, 18, 10, 1, tzinfo=timezone.utc)
    db_session.add_all([real, closed])
    await db_session.commit()

    count = await close_paper_trades_on_tick(db_session, _tick("1961.00", "1961.20"))

    assert count == 0
    assert real.close_price is None


def _trail_paper_trade(
    direction: Direction,
    open_price: str,
    rule_id: uuid.UUID,
    ticket: int = 7100,
) -> Trade:
    return Trade(
        id=uuid.uuid4(),
        ticket=ticket,
        symbol="XAUUSD",
        direction=direction,
        order_state=OrderState.filled,
        open_price=Decimal(open_price),
        volume=Decimal("0.10"),
        tp=Decimal("9999.00"),
        sl=Decimal("0.01"),
        open_time=datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
        is_paper=True,
        paper_mode=PaperMode.independent,
        paper_trader_rule_id=rule_id,
    )


def _trail_rule() -> PaperTraderRule:
    return PaperTraderRule(
        id=uuid.uuid4(),
        pattern_id=uuid.uuid4(),
        status="active",
        mode="basket_5k",
        virtual_balance_start=Decimal("5000"),
        virtual_balance_current=Decimal("5000"),
        trail_strategy="user_avg_trail",
    )


@pytest.mark.asyncio
async def test_arms_trail_when_unrealized_reaches_user_avg(db_session):
    rule = _trail_rule()
    db_session.add(rule)
    trade = _trail_paper_trade(Direction.buy, "1950.00", rule.id)
    db_session.add(trade)
    await db_session.commit()

    with patch(
        "services.paper_exit_manager.compute_user_avg_profit",
        new=AsyncMock(return_value=Decimal("500.00")),
    ):
        # Buy at 1950, bid 2000 → unrealized = 50 * 0.10 * 100 = 500.00 → arms.
        closed = await close_paper_trades_on_tick(db_session, _tick("2000.00", "2000.10"))

    assert closed == 0
    await db_session.refresh(trade)
    assert trade.close_time is None
    assert trade.recovery_plan is not None
    assert "trail" in trade.recovery_plan
    assert Decimal(trade.recovery_plan["trail"]["peak_profit"]) == Decimal("500.00")
    assert Decimal(trade.recovery_plan["trail"]["peak_price"]) == Decimal("2000.00")


@pytest.mark.asyncio
async def test_peak_updates_on_higher_unrealized(db_session):
    rule = _trail_rule()
    db_session.add(rule)
    trade = _trail_paper_trade(Direction.buy, "1950.00", rule.id, ticket=7110)
    trade.recovery_plan = {"trail": {"peak_profit": "500.00", "peak_price": "2000.00"}}
    db_session.add(trade)
    await db_session.commit()

    with patch(
        "services.paper_exit_manager.compute_user_avg_profit",
        new=AsyncMock(return_value=Decimal("500.00")),
    ):
        # Buy 1950, bid 2030 → unrealized = 80 * 0.10 * 100 = 800.00 > peak 500 → update.
        closed = await close_paper_trades_on_tick(db_session, _tick("2030.00", "2030.10"))

    assert closed == 0
    await db_session.refresh(trade)
    assert Decimal(trade.recovery_plan["trail"]["peak_profit"]) == Decimal("800.00")
    assert Decimal(trade.recovery_plan["trail"]["peak_price"]) == Decimal("2030.00")


@pytest.mark.asyncio
async def test_closes_on_retrace_and_writes_shadow_profit(db_session):
    rule = _trail_rule()
    db_session.add(rule)
    trade = _trail_paper_trade(Direction.buy, "1950.00", rule.id, ticket=7120)
    trade.recovery_plan = {"trail": {"peak_profit": "100.00", "peak_price": "1960.00"}}
    db_session.add(trade)
    await db_session.commit()

    with patch(
        "services.paper_exit_manager.compute_user_avg_profit",
        new=AsyncMock(return_value=Decimal("500.00")),
    ):
        # Buy 1950, bid 1958 → unrealized = 8 * 0.10 * 100 = 80.00 ≤ 80 (peak 100 * 0.80) → close.
        closed = await close_paper_trades_on_tick(db_session, _tick("1958.00", "1958.10"))

    assert closed == 1
    await db_session.refresh(trade)
    assert trade.close_price == Decimal("1958.00")
    assert trade.profit == Decimal("80.00")
    assert trade.paper_exit_reason == "user_avg_trail"
    assert trade.shadow_profit == Decimal("80.00")


@pytest.mark.asyncio
async def test_does_not_close_when_retrace_under_threshold(db_session):
    rule = _trail_rule()
    db_session.add(rule)
    trade = _trail_paper_trade(Direction.buy, "1950.00", rule.id, ticket=7130)
    trade.recovery_plan = {"trail": {"peak_profit": "100.00", "peak_price": "1960.00"}}
    db_session.add(trade)
    await db_session.commit()

    with patch(
        "services.paper_exit_manager.compute_user_avg_profit",
        new=AsyncMock(return_value=Decimal("500.00")),
    ):
        # Buy 1950, bid 1959 → unrealized = 9 * 0.10 * 100 = 90.00 > 80 → no close.
        closed = await close_paper_trades_on_tick(db_session, _tick("1959.00", "1959.10"))

    assert closed == 0
    await db_session.refresh(trade)
    assert trade.close_time is None


@pytest.mark.asyncio
async def test_no_trail_when_strategy_null(db_session):
    rule = _trail_rule()
    rule.trail_strategy = None
    db_session.add(rule)
    trade = _trail_paper_trade(Direction.buy, "1950.00", rule.id, ticket=7140)
    db_session.add(trade)
    await db_session.commit()

    with patch(
        "services.paper_exit_manager.compute_user_avg_profit",
        new=AsyncMock(return_value=Decimal("500.00")),
    ):
        closed = await close_paper_trades_on_tick(db_session, _tick("2000.00", "2000.10"))

    assert closed == 0
    await db_session.refresh(trade)
    assert trade.recovery_plan is None or "trail" not in (trade.recovery_plan or {})


@pytest.mark.asyncio
async def test_no_trail_when_user_avg_unavailable(db_session):
    rule = _trail_rule()
    db_session.add(rule)
    trade = _trail_paper_trade(Direction.buy, "1950.00", rule.id, ticket=7150)
    db_session.add(trade)
    await db_session.commit()

    with patch(
        "services.paper_exit_manager.compute_user_avg_profit",
        new=AsyncMock(return_value=None),
    ):
        closed = await close_paper_trades_on_tick(db_session, _tick("2000.00", "2000.10"))

    assert closed == 0
    await db_session.refresh(trade)
    assert trade.recovery_plan is None or "trail" not in (trade.recovery_plan or {})


@pytest.mark.asyncio
async def test_tp_wins_over_trail_on_same_tick(db_session):
    rule = _trail_rule()
    db_session.add(rule)
    trade = _trail_paper_trade(Direction.buy, "1950.00", rule.id, ticket=7160)
    trade.tp = Decimal("1955.00")
    trade.recovery_plan = {"trail": {"peak_profit": "100.00", "peak_price": "1960.00"}}
    db_session.add(trade)
    await db_session.commit()

    with patch(
        "services.paper_exit_manager.compute_user_avg_profit",
        new=AsyncMock(return_value=Decimal("500.00")),
    ):
        closed = await close_paper_trades_on_tick(db_session, _tick("1955.00", "1955.10"))

    assert closed == 1
    await db_session.refresh(trade)
    assert trade.paper_exit_reason == "tp"
    assert trade.close_price == Decimal("1955.00")
    assert trade.shadow_profit is None


@pytest.mark.asyncio
async def test_no_rule_link_skips_trail(db_session):
    trade = _paper_trade(Direction.buy, "1950.00", "9999.00", "0.01", ticket=7170)
    db_session.add(trade)
    await db_session.commit()

    with patch(
        "services.paper_exit_manager.compute_user_avg_profit",
        new=AsyncMock(return_value=Decimal("500.00")),
    ):
        closed = await close_paper_trades_on_tick(db_session, _tick("2000.00", "2000.10"))

    assert closed == 0
    await db_session.refresh(trade)
    assert trade.recovery_plan is None or "trail" not in (trade.recovery_plan or {})

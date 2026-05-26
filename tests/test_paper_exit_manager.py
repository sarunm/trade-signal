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

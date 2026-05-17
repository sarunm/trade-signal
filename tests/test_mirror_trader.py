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

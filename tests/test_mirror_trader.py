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


def _closed_trade(
    ticket: int,
    open_time: datetime,
    open_price: str,
    close_price: str,
    profit: str,
) -> Trade:
    return Trade(
        id=uuid.uuid4(),
        ticket=ticket,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal(open_price),
        close_price=Decimal(close_price),
        volume=Decimal("0.10"),
        profit=Decimal(profit),
        open_time=open_time,
        close_time=open_time,
        is_paper=False,
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
async def test_mirror_trade_copies_account_id(db_session):
    event = _entry_event()
    event.account_id = 335297575

    await create_mirror_trade(db_session, event)
    await db_session.commit()

    result = await db_session.execute(
        select(Trade).where(Trade.is_paper == True)
    )
    paper = result.scalar_one()
    assert paper.account_id == 335297575


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
    assert paper.paper_exit_strategy == "tp:direction_avg;sl:no_history"


@pytest.mark.asyncio
async def test_mirror_direction_sell(db_session):
    event = _entry_event(ticket=1002, direction="sell")
    await create_mirror_trade(db_session, event)
    await db_session.commit()

    result = await db_session.execute(select(Trade).where(Trade.is_paper == True))
    paper = result.scalars().first()
    assert paper.direction == Direction.sell


@pytest.mark.asyncio
async def test_mirror_exit_strategy_prefers_session_direction_history(db_session):
    london = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
    ny = datetime(2026, 5, 18, 15, 0, tzinfo=timezone.utc)
    db_session.add_all([
        _closed_trade(2001, london, "1900.00", "1930.00", "300.00"),
        _closed_trade(2002, london, "1910.00", "1940.00", "300.00"),
        _closed_trade(2003, london, "1900.00", "1880.00", "-200.00"),
        _closed_trade(2004, london, "1910.00", "1890.00", "-200.00"),
        _closed_trade(2005, ny, "1900.00", "1980.00", "800.00"),
        _closed_trade(2006, ny, "1910.00", "1990.00", "800.00"),
    ])
    await db_session.commit()

    event = _entry_event(ticket=3001, direction="buy")
    event.open_time = london
    await create_mirror_trade(db_session, event)
    await db_session.commit()

    result = await db_session.execute(select(Trade).where(Trade.is_paper == True))
    paper = result.scalars().first()
    assert paper.tp == Decimal("1980.00000")
    assert paper.sl == Decimal("1930.00000")
    assert paper.paper_exit_strategy == (
        "tp:session_direction_avg;sl:session_direction_avg"
    )

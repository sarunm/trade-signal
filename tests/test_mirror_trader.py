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
        symbol="GOLD#",
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
        symbol="GOLD#",
        direction="buy",
        order_type="market",
        order_state="filled",
        close_price=Decimal("1960.00"),
        close_time=datetime.now(timezone.utc),
        profit=Decimal("100.00"),
    )


@pytest.mark.asyncio
async def test_creates_mirror_trade_on_entry(db_session):
    await create_mirror_trade(db_session, _entry_event())
    await db_session.commit()

    rows = (await db_session.execute(select(Trade).where(Trade.is_paper == True))).scalars().all()
    assert len(rows) == 1
    paper = rows[0]
    assert paper.paper_mode == PaperMode.mirror
    assert paper.ticket == 1001
    assert float(paper.open_price) == pytest.approx(1950.00)


@pytest.mark.asyncio
async def test_mirror_does_not_set_tp_sl(db_session):
    """Spec: TP/SL are evaluated per tick; nothing pre-computed at spawn."""
    await create_mirror_trade(db_session, _entry_event())
    await db_session.commit()
    paper = (await db_session.execute(select(Trade).where(Trade.is_paper == True))).scalar_one()
    assert paper.tp is None
    assert paper.sl is None
    assert paper.paper_exit_strategy == "rule_driven"


@pytest.mark.asyncio
async def test_no_mirror_on_exit_event(db_session):
    await create_mirror_trade(db_session, _exit_event())
    await db_session.commit()
    rows = (await db_session.execute(select(Trade).where(Trade.is_paper == True))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_no_duplicate_mirror(db_session):
    await create_mirror_trade(db_session, _entry_event())
    await db_session.commit()
    await create_mirror_trade(db_session, _entry_event())
    await db_session.commit()
    rows = (await db_session.execute(select(Trade).where(Trade.is_paper == True))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_mirror_copies_account_id_and_direction(db_session):
    event = _entry_event(direction="sell")
    event.account_id = 335297575
    await create_mirror_trade(db_session, event)
    await db_session.commit()
    paper = (await db_session.execute(select(Trade).where(Trade.is_paper == True))).scalar_one()
    assert paper.account_id == 335297575
    assert paper.direction == Direction.sell

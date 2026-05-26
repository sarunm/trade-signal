from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models.pattern import PaperTraderRule, Pattern
from models.trade import Direction, OrderState, OrderType, PaperMode, Trade
from services.baseline_runner import (
    BASELINE_PATTERN_STATUS,
    BASELINE_RULE_MODE,
    ensure_baseline_rule,
    next_direction,
)


@pytest_asyncio.fixture
async def session():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(eng, expire_on_commit=False)
    async with Session() as s:
        yield s
    await eng.dispose()


@pytest.mark.asyncio
async def test_ensure_baseline_creates_pattern_and_rule(session):
    rule = await ensure_baseline_rule(session)
    assert rule is not None
    assert rule.mode == BASELINE_RULE_MODE

    patterns = (await session.execute(
        select(Pattern).where(Pattern.status == BASELINE_PATTERN_STATUS)
    )).scalars().all()
    assert len(patterns) == 1
    assert patterns[0].indicator_slugs == []


@pytest.mark.asyncio
async def test_ensure_baseline_idempotent(session):
    rule_a = await ensure_baseline_rule(session)
    rule_b = await ensure_baseline_rule(session)
    assert rule_a.id == rule_b.id
    patterns = (await session.execute(
        select(Pattern).where(Pattern.status == BASELINE_PATTERN_STATUS)
    )).scalars().all()
    assert len(patterns) == 1


def _baseline_trade(rule_id, direction: Direction, ticket: int, open_time: datetime) -> Trade:
    return Trade(
        ticket=ticket,
        symbol="XAUUSD",
        direction=direction,
        order_type=OrderType.market,
        order_state=OrderState.filled,
        open_time=open_time,
        open_price=Decimal("1950"),
        volume=Decimal("0.10"),
        is_paper=True,
        paper_mode=PaperMode.independent,
        recovery_plan={"paper_trader_rule_id": str(rule_id), "is_baseline": True},
    )


@pytest.mark.asyncio
async def test_first_baseline_trade_is_buy(session):
    rule = await ensure_baseline_rule(session)
    direction = await next_direction(session, rule)
    assert direction == Direction.buy


@pytest.mark.asyncio
async def test_alternates_after_buy(session):
    rule = await ensure_baseline_rule(session)
    session.add(_baseline_trade(
        rule.id, Direction.buy, ticket=1,
        open_time=datetime(2026, 5, 25, 7, 0, tzinfo=timezone.utc),
    ))
    await session.commit()
    direction = await next_direction(session, rule)
    assert direction == Direction.sell


@pytest.mark.asyncio
async def test_alternates_after_sell(session):
    rule = await ensure_baseline_rule(session)
    session.add(_baseline_trade(
        rule.id, Direction.sell, ticket=2,
        open_time=datetime(2026, 5, 25, 7, 0, tzinfo=timezone.utc),
    ))
    await session.commit()
    direction = await next_direction(session, rule)
    assert direction == Direction.buy

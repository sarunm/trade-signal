from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models.pattern import PaperTraderRule, Pattern
from models.trade import Direction, OrderState, OrderType, PaperMode, Trade
from services.adaptive_tuner import (
    ADAPTIVE_LOSS_DELTA,
    ADAPTIVE_MIN_BUCKET,
    FilterProposal,
    propose_filters_for_rule,
    spawn_shadow_rule,
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


async def _seed_rule(session) -> PaperTraderRule:
    pattern = Pattern(
        indicator_slugs=["rsi", "macd"], timeframe="H1",
        win_rate=0.55, sample_count=100, status="active",
    )
    session.add(pattern)
    await session.flush()
    rule = PaperTraderRule(
        pattern_id=pattern.id, status="active",
        mode="strict",
        virtual_balance_start=Decimal("5000"),
        virtual_balance_current=Decimal("5000"),
    )
    session.add(rule)
    await session.flush()
    return rule


def _trade(rule_id, *, profit: float, hour: int, dow: int = 0) -> Trade:
    open_t = datetime(2026, 4, 6 + dow, hour, 0, tzinfo=timezone.utc)  # 2026-04-06 = Mon
    return Trade(
        ticket=uuid4().int & 0x7FFFFFFF, symbol="XAUUSD",
        direction=Direction.buy,
        order_type=OrderType.market, order_state=OrderState.filled,
        open_time=open_t,
        close_time=open_t,
        open_price=Decimal("1950"), close_price=Decimal("1955"),
        volume=Decimal("0.10"),
        profit=Decimal(str(profit)),
        is_paper=True, paper_mode=PaperMode.independent,
        recovery_plan={"paper_trader_rule_id": str(rule_id)},
    )


@pytest.mark.asyncio
async def test_propose_filters_returns_session_excluder(session):
    rule = await _seed_rule(session)
    for _ in range(15):
        session.add(_trade(rule.id, profit=-50, hour=2))
    for _ in range(15):
        session.add(_trade(rule.id, profit=+50, hour=10))
    await session.commit()

    proposals = await propose_filters_for_rule(session, rule)

    assert any(
        p.feature == "session" and p.exclude == "asia"
        for p in proposals
    ), proposals


@pytest.mark.asyncio
async def test_propose_filters_skips_small_buckets(session):
    rule = await _seed_rule(session)
    for _ in range(5):
        session.add(_trade(rule.id, profit=-50, hour=2))
    for _ in range(20):
        session.add(_trade(rule.id, profit=+50, hour=10))
    await session.commit()
    proposals = await propose_filters_for_rule(session, rule)
    assert not any(p.feature == "session" and p.exclude == "asia" for p in proposals)


@pytest.mark.asyncio
async def test_propose_filters_skips_when_delta_below_threshold(session):
    rule = await _seed_rule(session)
    for i in range(16):
        session.add(_trade(rule.id, profit=+50 if i < 8 else -50, hour=2))
    for i in range(16):
        session.add(_trade(rule.id, profit=+50 if i < 9 else -50, hour=10))
    await session.commit()
    proposals = await propose_filters_for_rule(session, rule)
    assert not any(p.feature == "session" for p in proposals)


@pytest.mark.asyncio
async def test_spawn_shadow_creates_rule_with_filter_and_parent_link(session):
    rule = await _seed_rule(session)
    proposal = FilterProposal(
        feature="session", exclude="asia",
        bucket_n=12, bucket_loss_rate=1.0, other_loss_rate=0.0,
    )
    shadow = await spawn_shadow_rule(session, rule, proposal)
    assert shadow.id != rule.id
    assert shadow.status == "shadow"
    assert shadow.shadow_of_rule_id == rule.id
    assert shadow.pattern_id == rule.pattern_id
    assert shadow.mode == rule.mode
    assert shadow.filters == [{"feature": "session", "exclude": "asia"}]


@pytest.mark.asyncio
async def test_spawn_shadow_is_idempotent_for_same_proposal(session):
    rule = await _seed_rule(session)
    proposal = FilterProposal(
        feature="session", exclude="asia",
        bucket_n=12, bucket_loss_rate=1.0, other_loss_rate=0.0,
    )
    a = await spawn_shadow_rule(session, rule, proposal)
    b = await spawn_shadow_rule(session, rule, proposal)
    assert a.id == b.id

    rules = (await session.execute(
        select(PaperTraderRule).where(PaperTraderRule.shadow_of_rule_id == rule.id)
    )).scalars().all()
    assert len(rules) == 1

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

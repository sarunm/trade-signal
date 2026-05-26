from datetime import datetime, timezone
from decimal import Decimal

import pytest

from services.signal_broadcaster import (
    SignalEvalInputs,
    STATUS_ACTIVE,
    STATUS_NEAR,
    STATUS_FAR,
    STATUS_IDLE,
    compute_status,
)


def test_status_active_when_all_match():
    inputs = SignalEvalInputs(matched_count=4, total_count=4, has_open_paper=False)
    assert compute_status(inputs) == STATUS_ACTIVE


def test_status_near_when_one_missing_of_three_or_more():
    inputs = SignalEvalInputs(matched_count=3, total_count=4, has_open_paper=False)
    assert compute_status(inputs) == STATUS_NEAR


def test_status_far_when_some_match_but_not_near():
    inputs = SignalEvalInputs(matched_count=2, total_count=5, has_open_paper=False)
    assert compute_status(inputs) == STATUS_FAR


def test_status_idle_when_no_match():
    inputs = SignalEvalInputs(matched_count=0, total_count=4, has_open_paper=False)
    assert compute_status(inputs) == STATUS_IDLE


def test_status_active_when_open_paper_overrides():
    inputs = SignalEvalInputs(matched_count=1, total_count=5, has_open_paper=True)
    assert compute_status(inputs) == STATUS_ACTIVE


import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models.pattern import PaperTraderRule, Pattern
from services.signal_broadcaster import (
    RuleEval,
    broadcast_status_changes,
    reset_broadcaster_state,
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


async def _seed_rule(session, status="active") -> PaperTraderRule:
    pattern = Pattern(
        indicator_slugs=["rsi_14", "ema_50"],
        timeframe="H1",
        win_rate=0.7,
        sample_count=20,
        status="active",
    )
    session.add(pattern)
    await session.flush()
    rule = PaperTraderRule(pattern_id=pattern.id, status=status, mode="strict")
    session.add(rule)
    await session.commit()
    return rule


@pytest.mark.asyncio
async def test_broadcasts_when_status_changes(session):
    reset_broadcaster_state()
    rule = await _seed_rule(session)

    evals = [
        RuleEval(
            rule_id=rule.id,
            inputs=SignalEvalInputs(matched_count=2, total_count=2, has_open_paper=False),
            matched_conditions=["rsi_14", "ema_50"],
            missing_conditions=[],
            score=80.0,
            suggested_lot=Decimal("0.05"),
        )
    ]
    now = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)
    written = await broadcast_status_changes(session, evals, now=now)
    assert len(written) == 1
    assert written[0].status == STATUS_ACTIVE


@pytest.mark.asyncio
async def test_no_broadcast_when_status_unchanged(session):
    reset_broadcaster_state()
    rule = await _seed_rule(session)
    evals = [
        RuleEval(
            rule_id=rule.id,
            inputs=SignalEvalInputs(matched_count=2, total_count=2, has_open_paper=False),
            matched_conditions=["rsi_14", "ema_50"],
            missing_conditions=[],
        )
    ]
    now = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)
    await broadcast_status_changes(session, evals, now=now)
    second = await broadcast_status_changes(session, evals, now=now)
    assert second == []


@pytest.mark.asyncio
async def test_broadcasts_again_when_status_flips(session):
    reset_broadcaster_state()
    rule = await _seed_rule(session)
    e_active = [RuleEval(
        rule_id=rule.id,
        inputs=SignalEvalInputs(matched_count=2, total_count=2, has_open_paper=False),
        matched_conditions=["rsi_14", "ema_50"], missing_conditions=[],
    )]
    e_far = [RuleEval(
        rule_id=rule.id,
        inputs=SignalEvalInputs(matched_count=1, total_count=4, has_open_paper=False),
        matched_conditions=["rsi_14"], missing_conditions=["ema_50", "macd", "atr"],
    )]
    now = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)
    await broadcast_status_changes(session, e_active, now=now)
    flipped = await broadcast_status_changes(session, e_far, now=now)
    assert len(flipped) == 1
    assert flipped[0].status == STATUS_FAR

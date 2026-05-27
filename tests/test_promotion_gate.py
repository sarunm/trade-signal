from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models.pattern import PaperTraderRule, Pattern
from models.trade import Direction, OrderState, OrderType, PaperMode, Trade
from services.promotion_gate import (
    PROMOTION_MIN_BASELINE_DELTA,
    PROMOTION_MIN_TRADES,
    PROMOTION_MIN_WILSON_LOWER,
    PROMOTION_STABLE_DAYS,
    evaluate_rule,
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


async def _seed_rule(session, total_trades=0, win_count=0) -> PaperTraderRule:
    pattern = Pattern(
        indicator_slugs=["rsi_14", "ema_50"], timeframe="H1",
        win_rate=0.6, sample_count=20, status="active",
    )
    session.add(pattern)
    await session.flush()
    rule = PaperTraderRule(
        pattern_id=pattern.id, status="active", mode="basket_5k",
        total_trades=total_trades, win_count=win_count,
    )
    session.add(rule)
    await session.commit()
    return rule


async def _seed_baseline_with_winrate(session, winrate: float, trades: int = 50):
    from services.baseline_runner import ensure_baseline_rule
    base = datetime.now(timezone.utc) - timedelta(days=10)
    rule = await ensure_baseline_rule(session)
    for i in range(trades):
        is_win = (i / trades) < winrate
        session.add(Trade(
            ticket=10_000 + i,
            symbol="GOLD#",
            direction=Direction.buy,
            order_type=OrderType.market, order_state=OrderState.filled,
            open_time=base + timedelta(hours=i),
            close_time=base + timedelta(hours=i, minutes=30),
            open_price=Decimal("1950"),
            close_price=Decimal("1955" if is_win else "1945"),
            volume=Decimal("0.10"),
            profit=Decimal("100" if is_win else "-100"),
            is_paper=True, paper_mode=PaperMode.independent,
            recovery_plan={"paper_trader_rule_id": str(rule.id), "is_baseline": True},
        ))
    await session.commit()


async def _seed_paper_history(
    session, rule_id, total: int, winrate: float,
    profit_each_win=Decimal("100"), profit_each_loss=Decimal("-50"),
    ticket_base: int = 20_000,
):
    base = datetime.now(timezone.utc) - timedelta(days=10)
    for i in range(total):
        is_win = (i / total) < winrate
        session.add(Trade(
            ticket=ticket_base + i,
            symbol="GOLD#",
            direction=Direction.buy,
            order_type=OrderType.market, order_state=OrderState.filled,
            open_time=base + timedelta(hours=i),
            close_time=base + timedelta(hours=i, minutes=30),
            open_price=Decimal("1950"),
            close_price=Decimal("1955" if is_win else "1945"),
            volume=Decimal("0.10"),
            profit=profit_each_win if is_win else profit_each_loss,
            is_paper=True, paper_mode=PaperMode.independent,
            recovery_plan={"paper_trader_rule_id": str(rule_id)},
        ))
    await session.commit()


# -----------------------------------------------------------------------------
# Gate 1 — sample sufficiency
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sample_gate_fails_below_threshold(session):
    rule = await _seed_rule(session, total_trades=PROMOTION_MIN_TRADES - 1)
    result = await evaluate_rule(session, rule)
    assert result.gates.sample is False
    assert result.tier == "experimental"


@pytest.mark.asyncio
async def test_sample_gate_passes_at_threshold(session):
    rule = await _seed_rule(session, total_trades=PROMOTION_MIN_TRADES, win_count=70)
    await _seed_paper_history(session, rule.id, total=PROMOTION_MIN_TRADES, winrate=0.70)
    result = await evaluate_rule(session, rule)
    assert result.gates.sample is True


# -----------------------------------------------------------------------------
# Gate 2 — Wilson + net EV + baseline
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_performance_gate_passes_with_strong_stats(session):
    await _seed_baseline_with_winrate(session, winrate=0.5)
    rule = await _seed_rule(session, total_trades=100, win_count=70)
    await _seed_paper_history(session, rule.id, total=100, winrate=0.7)
    result = await evaluate_rule(session, rule)
    assert result.gates.performance is True
    assert result.tier == "validated"
    assert result.wilson_lower >= PROMOTION_MIN_WILSON_LOWER
    assert result.baseline_delta >= PROMOTION_MIN_BASELINE_DELTA


@pytest.mark.asyncio
async def test_performance_gate_fails_when_not_beating_baseline(session):
    await _seed_baseline_with_winrate(session, winrate=0.7)
    rule = await _seed_rule(session, total_trades=100, win_count=72)
    await _seed_paper_history(session, rule.id, total=100, winrate=0.72)
    result = await evaluate_rule(session, rule)
    assert result.gates.performance is False
    assert "baseline" in result.reason


@pytest.mark.asyncio
async def test_performance_gate_fails_when_low_net_ev(session):
    await _seed_baseline_with_winrate(session, winrate=0.5)
    rule = await _seed_rule(session, total_trades=100, win_count=60)
    # 60 wins x ฿1, 40 losses x -฿2 ⇒ net EV negative
    await _seed_paper_history(
        session, rule.id, total=100, winrate=0.6,
        profit_each_win=Decimal("1"), profit_each_loss=Decimal("-2"),
    )
    result = await evaluate_rule(session, rule)
    assert result.gates.performance is False
    assert "ev" in result.reason or "profit_factor" in result.reason


# -----------------------------------------------------------------------------
# Gate 3 — stability
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stability_gate_passes_at_threshold(session):
    await _seed_baseline_with_winrate(session, winrate=0.5)
    rule = await _seed_rule(session, total_trades=100, win_count=70)
    rule.consecutive_stable_days_rule = PROMOTION_STABLE_DAYS - 1
    await session.commit()
    await _seed_paper_history(session, rule.id, total=100, winrate=0.7)
    result = await evaluate_rule(session, rule)
    # After Gate 2 pass, counter bumps by 1 → reaches threshold
    assert result.gates.stability is True
    assert result.tier in ("live_proven", "ea_candidate")


@pytest.mark.asyncio
async def test_stability_gate_fails_below_threshold(session):
    await _seed_baseline_with_winrate(session, winrate=0.5)
    rule = await _seed_rule(session, total_trades=100, win_count=70)
    rule.consecutive_stable_days_rule = 0
    await session.commit()
    await _seed_paper_history(session, rule.id, total=100, winrate=0.7)
    result = await evaluate_rule(session, rule)
    # bumps to 1 after Gate 2 pass — still below PROMOTION_STABLE_DAYS=7
    assert result.gates.stability is False
    assert result.tier == "validated"


# -----------------------------------------------------------------------------
# Gate 4 — walk-forward
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_walk_forward_passes_with_held_out_window(session):
    await _seed_baseline_with_winrate(session, winrate=0.5)
    rule = await _seed_rule(session, total_trades=100, win_count=70)
    rule.consecutive_stable_days_rule = PROMOTION_STABLE_DAYS - 1
    await session.commit()
    # Bulk window: older trades
    await _seed_paper_history(session, rule.id, total=100, winrate=0.7, ticket_base=20_000)
    # Held-out window: recent (within walk-forward) trades
    base = datetime.now(timezone.utc) - timedelta(days=5)
    for i in range(40):
        is_win = (i / 40) < 0.7
        session.add(Trade(
            ticket=30_000 + i,
            symbol="GOLD#",
            direction=Direction.buy,
            order_type=OrderType.market, order_state=OrderState.filled,
            open_time=base + timedelta(hours=i),
            close_time=base + timedelta(hours=i, minutes=30),
            open_price=Decimal("1950"),
            close_price=Decimal("1955" if is_win else "1945"),
            volume=Decimal("0.10"),
            profit=Decimal("100" if is_win else "-50"),
            is_paper=True, paper_mode=PaperMode.independent,
            recovery_plan={"paper_trader_rule_id": str(rule.id)},
        ))
    await session.commit()
    result = await evaluate_rule(session, rule)
    assert result.gates.walk_forward is True
    assert result.tier == "ea_candidate"


# -----------------------------------------------------------------------------
# Stability counter — auto-bump/reset
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stable_days_increments_when_performance_passes(session):
    await _seed_baseline_with_winrate(session, winrate=0.5)
    rule = await _seed_rule(session, total_trades=100, win_count=70)
    await _seed_paper_history(session, rule.id, total=100, winrate=0.7)
    before = rule.consecutive_stable_days_rule or 0
    await evaluate_rule(session, rule)
    await session.refresh(rule)
    assert rule.consecutive_stable_days_rule == before + 1


@pytest.mark.asyncio
async def test_stable_days_resets_when_performance_fails(session):
    await _seed_baseline_with_winrate(session, winrate=0.7)
    rule = await _seed_rule(session, total_trades=100, win_count=72)
    rule.consecutive_stable_days_rule = 5
    await session.commit()
    await _seed_paper_history(session, rule.id, total=100, winrate=0.72)
    await evaluate_rule(session, rule)
    await session.refresh(rule)
    assert rule.consecutive_stable_days_rule == 0

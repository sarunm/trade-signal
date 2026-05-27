import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from models.indicator_signal import TradeIndicatorSignal
from models.pattern import PaperTraderRule, Pattern
from models.trade import Direction, OrderState, OrderType, Trade
from services import pattern_discovery
from services.pattern_discovery import (
    BASKET_CLOSE_GAP_SEC,
    MINING_MAX_BASKET_SIZE,
    group_into_baskets,
    run_pattern_discovery,
)


def _real_trade(close_time, profit, volume="0.10", ticket=None):
    return Trade(
        ticket=ticket or int(close_time.timestamp() * 1000) % 10**9,
        symbol="GOLD#",
        direction=Direction.buy,
        order_type=OrderType.market,
        order_state=OrderState.filled,
        open_time=close_time - timedelta(minutes=5),
        close_time=close_time,
        open_price=Decimal("1950.00"),
        close_price=Decimal("1955.00"),
        volume=Decimal(volume),
        profit=Decimal(str(profit)),
        is_paper=False,
    )


def test_group_into_baskets_close_within_gap():
    base = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    a = _real_trade(base, profit=10, volume="0.01", ticket=1)
    b = _real_trade(base + timedelta(seconds=1), profit=-5, volume="0.05", ticket=2)
    baskets = group_into_baskets([(a, set()), (b, set())])
    assert len(baskets) == 1
    assert {t.ticket for t, _ in baskets[0]} == {1, 2}


def test_group_into_baskets_far_apart():
    base = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    a = _real_trade(base, profit=10, ticket=1)
    b = _real_trade(base + timedelta(seconds=10), profit=20, ticket=2)
    baskets = group_into_baskets([(a, set()), (b, set())])
    assert len(baskets) == 2


def test_group_into_baskets_max_size():
    base = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    trades = [
        _real_trade(base + timedelta(milliseconds=i * 200), profit=1, ticket=i + 1)
        for i in range(MINING_MAX_BASKET_SIZE + 2)
    ]
    baskets = group_into_baskets([(t, set()) for t in trades])
    sizes = [len(b) for b in baskets]
    assert max(sizes) == MINING_MAX_BASKET_SIZE


def _trade(profit: float, close_time: datetime, ticket: int = 0) -> Trade:
    return Trade(
        ticket=ticket or int(close_time.timestamp()),
        symbol="GOLD#",
        direction=Direction.buy,
        is_paper=False,
        open_price=Decimal("1900"),
        close_price=Decimal("1905") if profit > 0 else Decimal("1895"),
        close_time=close_time,
        open_time=close_time - timedelta(hours=1),
        profit=Decimal(str(profit)),
        volume=Decimal("0.10"),
    )


def _signals(trade: Trade, slugs: list[str]):
    out = []
    for slug in slugs:
        out.append(
            TradeIndicatorSignal(
                trade_id=trade.id,
                indicator_slug=slug,
                timeframe="H1",
                value=1.0,
                direction="bullish",
                matched=True,
                metadata={},
                calculated_at=trade.close_time,
            )
        )
    return out


async def _seed_trades(session, recipes: list[tuple[float, datetime, list[str]]]):
    """recipes: list of (profit, close_time, matched_slugs)."""
    for i, (profit, close_time, slugs) in enumerate(recipes, start=1):
        trade = _trade(profit, close_time, ticket=10000 + i)
        session.add(trade)
        await session.flush()
        for sig in _signals(trade, slugs):
            session.add(sig)
    await session.commit()


@pytest.mark.asyncio
async def test_jaccard_similarity():
    assert pattern_discovery.jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert pattern_discovery.jaccard({"a", "b"}, {"c", "d"}) == 0.0
    assert pattern_discovery.jaccard({"a", "b", "c"}, {"a", "b", "d"}) == 0.5


@pytest.mark.asyncio
async def test_run_creates_candidate_below_stable_threshold(db_session, monkeypatch):
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_MIN_SAMPLE", 5)
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_MIN_WIN_RATE", 0.6)
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_STABLE_DAYS", 3)

    now = datetime(2026, 5, 25, 12, tzinfo=timezone.utc)
    recipes = [
        (50.0, now - timedelta(days=1), ["rsi", "macd"]),
        (40.0, now - timedelta(days=2), ["rsi", "macd"]),
        (30.0, now - timedelta(days=3), ["rsi", "macd"]),
        (20.0, now - timedelta(days=4), ["rsi", "macd"]),
        (-10.0, now - timedelta(days=5), ["rsi", "macd"]),
    ]
    await _seed_trades(db_session, recipes)

    await pattern_discovery.run_pattern_discovery(session=db_session, now=now)

    result = await db_session.execute(select(Pattern))
    patterns = result.scalars().all()

    rsi_macd = next(
        (p for p in patterns if set(p.indicator_slugs) == {"rsi", "macd"}), None
    )
    assert rsi_macd is not None
    assert rsi_macd.status == "candidate"
    assert rsi_macd.consecutive_stable_days == 1
    assert rsi_macd.win_rate == pytest.approx(0.8)
    assert rsi_macd.sample_count == 5

    rules = (await db_session.execute(select(PaperTraderRule))).scalars().all()
    assert rules == []


@pytest.mark.asyncio
async def test_run_promotes_after_stable_days_and_spawns_rule(db_session, monkeypatch):
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_MIN_SAMPLE", 5)
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_MIN_WIN_RATE", 0.6)
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_STABLE_DAYS", 2)

    now = datetime(2026, 5, 25, 12, tzinfo=timezone.utc)
    recipes = [
        (50.0, now - timedelta(days=1), ["rsi", "macd"]),
        (40.0, now - timedelta(days=2), ["rsi", "macd"]),
        (30.0, now - timedelta(days=3), ["rsi", "macd"]),
        (20.0, now - timedelta(days=4), ["rsi", "macd"]),
        (-10.0, now - timedelta(days=5), ["rsi", "macd"]),
    ]
    await _seed_trades(db_session, recipes)

    await pattern_discovery.run_pattern_discovery(session=db_session, now=now)
    await pattern_discovery.run_pattern_discovery(
        session=db_session, now=now + timedelta(days=1)
    )

    patterns = (await db_session.execute(select(Pattern))).scalars().all()
    rsi_macd = next(p for p in patterns if set(p.indicator_slugs) == {"rsi", "macd"})
    assert rsi_macd.status == "active"
    assert rsi_macd.consecutive_stable_days == 2
    assert rsi_macd.promoted_at is not None

    rules = (await db_session.execute(select(PaperTraderRule))).scalars().all()
    assert len(rules) == 3
    assert all(r.pattern_id == rsi_macd.id for r in rules)
    assert all(r.status == "active" for r in rules)
    assert sorted(r.mode for r in rules) == ["basket_50k", "basket_5k", "strict"]


@pytest.mark.asyncio
async def test_run_resets_consecutive_days_when_threshold_failed(db_session, monkeypatch):
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_MIN_SAMPLE", 5)
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_MIN_WIN_RATE", 0.6)
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_STABLE_DAYS", 3)

    now = datetime(2026, 5, 25, 12, tzinfo=timezone.utc)
    recipes_pass = [
        (50.0, now - timedelta(days=1), ["rsi", "macd"]),
        (40.0, now - timedelta(days=2), ["rsi", "macd"]),
        (30.0, now - timedelta(days=3), ["rsi", "macd"]),
        (20.0, now - timedelta(days=4), ["rsi", "macd"]),
        (-10.0, now - timedelta(days=5), ["rsi", "macd"]),
    ]
    await _seed_trades(db_session, recipes_pass)
    await pattern_discovery.run_pattern_discovery(session=db_session, now=now)

    pat = (await db_session.execute(select(Pattern))).scalars().first()
    assert pat.consecutive_stable_days == 1

    next_day = now + timedelta(days=1)
    later_recipes = [
        (-10.0, next_day - timedelta(hours=1), ["rsi", "macd"]),
        (-10.0, next_day - timedelta(hours=2), ["rsi", "macd"]),
        (-10.0, next_day - timedelta(hours=3), ["rsi", "macd"]),
        (-10.0, next_day - timedelta(hours=4), ["rsi", "macd"]),
        (-10.0, next_day - timedelta(hours=5), ["rsi", "macd"]),
    ]
    await _seed_trades(db_session, later_recipes)
    await pattern_discovery.run_pattern_discovery(session=db_session, now=next_day)

    await db_session.refresh(pat)
    assert pat.consecutive_stable_days == 0
    assert pat.status == "candidate"


@pytest.mark.asyncio
async def test_run_skips_dedup_with_high_jaccard(db_session, monkeypatch):
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_MIN_SAMPLE", 4)
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_MIN_WIN_RATE", 0.6)
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_STABLE_DAYS", 1)

    existing_pattern = Pattern(
        indicator_slugs=["rsi", "macd"],
        timeframe="H1",
        win_rate=0.7,
        sample_count=10,
        consecutive_stable_days=3,
        status="active",
        promoted_at=datetime.now(timezone.utc),
    )
    db_session.add(existing_pattern)
    await db_session.flush()
    db_session.add(
        PaperTraderRule(pattern_id=existing_pattern.id, status="active")
    )
    await db_session.commit()

    now = datetime(2026, 5, 25, 12, tzinfo=timezone.utc)
    recipes = [
        (50.0, now - timedelta(days=1), ["rsi", "macd"]),
        (40.0, now - timedelta(days=2), ["rsi", "macd"]),
        (30.0, now - timedelta(days=3), ["rsi", "macd"]),
        (-10.0, now - timedelta(days=4), ["rsi", "macd"]),
    ]
    await _seed_trades(db_session, recipes)

    await pattern_discovery.run_pattern_discovery(session=db_session, now=now)

    rules = (await db_session.execute(select(PaperTraderRule))).scalars().all()
    assert len(rules) == 1, f"new rule should be deduplicated, got {len(rules)} rules"


@pytest.mark.asyncio
async def test_run_filters_below_min_sample_or_win_rate(db_session, monkeypatch):
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_MIN_SAMPLE", 10)
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_MIN_WIN_RATE", 0.6)
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_STABLE_DAYS", 3)

    now = datetime(2026, 5, 25, 12, tzinfo=timezone.utc)
    recipes = [
        (50.0, now - timedelta(days=1), ["rsi", "macd"]),
        (-10.0, now - timedelta(days=2), ["rsi", "macd"]),
    ]
    await _seed_trades(db_session, recipes)

    await pattern_discovery.run_pattern_discovery(session=db_session, now=now)

    patterns = (await db_session.execute(select(Pattern))).scalars().all()
    assert patterns == []


@pytest.mark.asyncio
async def test_run_respects_window(db_session, monkeypatch):
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_MIN_SAMPLE", 5)
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_MIN_WIN_RATE", 0.6)
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_STABLE_DAYS", 3)
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_WINDOW_TRADES", 5)
    monkeypatch.setattr(pattern_discovery, "DISCOVERY_WINDOW_MAX_DAYS", 30)

    now = datetime(2026, 5, 25, 12, tzinfo=timezone.utc)
    recent = [
        (50.0, now - timedelta(days=1), ["rsi", "macd"]),
        (40.0, now - timedelta(days=2), ["rsi", "macd"]),
        (30.0, now - timedelta(days=3), ["rsi", "macd"]),
        (20.0, now - timedelta(days=4), ["rsi", "macd"]),
        (-10.0, now - timedelta(days=5), ["rsi", "macd"]),
    ]
    losing_old = [
        (-100.0, now - timedelta(days=20), ["rsi", "macd"]),
        (-100.0, now - timedelta(days=21), ["rsi", "macd"]),
        (-100.0, now - timedelta(days=22), ["rsi", "macd"]),
        (-100.0, now - timedelta(days=23), ["rsi", "macd"]),
    ]
    await _seed_trades(db_session, recent + losing_old)

    await pattern_discovery.run_pattern_discovery(session=db_session, now=now)

    pat = (await db_session.execute(select(Pattern))).scalars().first()
    assert pat is not None
    assert pat.sample_count == 5
    assert pat.win_rate == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_api_returns_patterns_and_rules(client, db_session):
    pattern = Pattern(
        indicator_slugs=["rsi", "macd"],
        timeframe="H1",
        win_rate=0.75,
        sample_count=12,
        consecutive_stable_days=3,
        status="active",
        promoted_at=datetime.now(timezone.utc),
    )
    db_session.add(pattern)
    await db_session.flush()
    db_session.add(
        PaperTraderRule(
            pattern_id=pattern.id, status="active", total_trades=4, win_count=3
        )
    )
    await db_session.commit()

    resp = await client.get("/api/patterns")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["indicator_slugs"] == ["rsi", "macd"]
    assert body[0]["status"] == "active"

    resp = await client.get("/api/paper-trader-rules?status=active")
    assert resp.status_code == 200
    rules = resp.json()
    assert len(rules) == 1
    assert rules[0]["total_trades"] == 4
    assert rules[0]["win_rate"] == pytest.approx(0.75)


def test_basket_anchor_is_first_trade_slugs():
    base = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    a = _real_trade(base, profit=-50, volume="0.01", ticket=1)
    b = _real_trade(base + timedelta(seconds=1), profit=200, volume="0.10", ticket=2)
    population = [(a, {"ema_50_h1", "rsi_14_h1"}), (b, {"macd_h1", "atr_h1"})]
    baskets = group_into_baskets(population)
    from services.pattern_discovery import _basket_anchor_slugs, _basket_outcome
    assert _basket_anchor_slugs(baskets[0]) == {"ema_50_h1", "rsi_14_h1"}


def test_basket_outcome_size_weighted_win():
    base = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    starter = _real_trade(base, profit=-50, volume="0.01", ticket=1)
    rescue = _real_trade(base + timedelta(seconds=1), profit=200, volume="0.10", ticket=2)
    from services.pattern_discovery import _basket_outcome
    assert _basket_outcome([(starter, set()), (rescue, set())]) is True


def test_basket_outcome_size_weighted_loss():
    base = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
    starter = _real_trade(base, profit=10, volume="0.01", ticket=1)
    rescue = _real_trade(base + timedelta(seconds=1), profit=-100, volume="0.10", ticket=2)
    from services.pattern_discovery import _basket_outcome
    assert _basket_outcome([(starter, set()), (rescue, set())]) is False


@pytest_asyncio.fixture
async def db_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from database import Base

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


async def _seed_basket_runs(session, n_baskets: int, all_win: bool, slugs: tuple[str, ...]):
    base = datetime(2026, 5, 25, tzinfo=timezone.utc)
    for i in range(n_baskets):
        close_time = base + timedelta(hours=i)
        a = _real_trade(close_time, profit=20 if all_win else -20, ticket=i * 10 + 1)
        b = _real_trade(close_time + timedelta(milliseconds=200),
                         profit=10 if all_win else -10, ticket=i * 10 + 2)
        session.add_all([a, b])
        await session.flush()
        for slug in slugs:
            session.add(TradeIndicatorSignal(
                trade_id=a.id, indicator_slug=slug, matched=True, timeframe="H1",
            ))
    await session.commit()


@pytest.mark.asyncio
async def test_promotion_spawns_three_variants(db_session):
    await _seed_basket_runs(
        db_session, n_baskets=15, all_win=True, slugs=("ema_50_h1", "rsi_14_h1"),
    )
    # Run 3 days for stability
    base = datetime(2026, 5, 28, tzinfo=timezone.utc)
    for i in range(3):
        await run_pattern_discovery(db_session, now=base + timedelta(days=i))

    rules = (await db_session.execute(select(PaperTraderRule))).scalars().all()
    modes = sorted(r.mode for r in rules)
    assert modes == ["basket_50k", "basket_5k", "strict"]
    by_mode = {r.mode: r for r in rules}
    assert by_mode["strict"].virtual_balance_start == Decimal("5000")
    assert by_mode["basket_5k"].virtual_balance_start == Decimal("5000")
    assert by_mode["basket_50k"].virtual_balance_start == Decimal("50000")

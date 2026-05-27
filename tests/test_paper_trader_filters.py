from datetime import datetime, timedelta, timezone

import pytest

from services.paper_trader import _passes_filters


def _ctx(now: datetime) -> dict:
    return {"now": now}


def test_passes_when_no_filters():
    rule = type("R", (), {"filters": []})()
    assert _passes_filters(rule, _ctx(datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)))


def test_rejects_when_session_excluded():
    rule = type("R", (), {"filters": [{"feature": "session", "exclude": "asia"}]})()
    asia_now = datetime(2026, 5, 25, 2, 0, tzinfo=timezone.utc)
    assert not _passes_filters(rule, _ctx(asia_now))


def test_passes_when_session_does_not_match_excluded():
    rule = type("R", (), {"filters": [{"feature": "session", "exclude": "asia"}]})()
    london_now = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)
    assert _passes_filters(rule, _ctx(london_now))


def test_rejects_on_hour_bucket_exclude():
    rule = type("R", (), {"filters": [{"feature": "hour_bucket", "exclude": "00-04"}]})()
    early_now = datetime(2026, 5, 25, 2, 0, tzinfo=timezone.utc)
    assert not _passes_filters(rule, _ctx(early_now))


def test_rejects_on_dow_exclude():
    rule = type("R", (), {"filters": [{"feature": "dow", "exclude": "fri"}]})()
    fri_now = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)  # Fri
    assert not _passes_filters(rule, _ctx(fri_now))


def test_rejects_on_unknown_feature_passes_through():
    rule = type("R", (), {"filters": [{"feature": "novel", "exclude": "x"}]})()
    assert _passes_filters(rule, _ctx(datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)))


# ── Integration: filter gate inside run_paper_trader ──────────────
import uuid
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models.pattern import PaperTraderRule, Pattern
from models.price_bar import PriceBar, Timeframe
from models.trade import Trade
from schemas.market_tick import MarketTickSchema
from services import paper_trader
from services.indicators.common import IndicatorSpec


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


@pytest.fixture(autouse=True)
def _reset_paper_trader():
    paper_trader.reset_cache()
    paper_trader.reset_slow_path()
    yield
    paper_trader.reset_cache()
    paper_trader.reset_slow_path()


@pytest.fixture
def fake_specs(monkeypatch):
    state = {"slug_directions": {}, "atr": 5.0,
             "pivot_meta": {"r1": 1910.0, "r2": 1925.0, "s1": 1890.0, "s2": 1875.0}}

    def fake_compute(slug):
        def _c(df):
            return 1.0, state["slug_directions"].get(slug, "neutral"), {}
        return _c

    def fake_pivot(df):
        return 1900.0, "neutral", dict(state["pivot_meta"])

    def fake_atr(df, length):
        import pandas as pd
        return pd.Series([state["atr"]] * len(df))

    def setup(slugs):
        registry = {s: IndicatorSpec(s, "momentum", fake_compute(s)) for s in slugs}
        registry["pivot_std"] = IndicatorSpec("pivot_std", "sr", fake_pivot)
        monkeypatch.setattr(paper_trader, "ALL_SPECS", registry)
        monkeypatch.setattr(paper_trader, "SR_SPECS", {"pivot_std": registry["pivot_std"]})
        monkeypatch.setattr(paper_trader, "_atr", fake_atr)

    return type("F", (), {"setup": staticmethod(setup), "state": state})


async def _seed_pattern_rule_with_filter(session, filters):
    pattern = Pattern(
        indicator_slugs=["rsi", "macd"], timeframe="H1",
        win_rate=0.7, sample_count=10, consecutive_stable_days=3,
        status="active",
    )
    session.add(pattern)
    await session.flush()
    rule = PaperTraderRule(
        pattern_id=pattern.id, status="active", mode="strict",
        filters=filters,
    )
    session.add(rule)
    await session.commit()
    return rule


async def _seed_bars_at(session, anchor: datetime, count=30, base=1900.0):
    for i in range(count):
        session.add(
            PriceBar(
                time=anchor - timedelta(hours=count - i),
                symbol="GOLD#", timeframe=Timeframe.H1,
                open=Decimal(str(base + i * 0.1)),
                high=Decimal(str(base + i * 0.1 + 1)),
                low=Decimal(str(base + i * 0.1 - 1)),
                close=Decimal(str(base + i * 0.1 + 0.5)),
                volume=Decimal("100"),
            )
        )
    await session.commit()


def _tick(now: datetime, bid=1900.0, ask=1900.5) -> MarketTickSchema:
    return MarketTickSchema(timestamp=now, symbol="GOLD#",
                            bid=Decimal(str(bid)), ask=Decimal(str(ask)))


@pytest.mark.asyncio
async def test_run_paper_trader_skips_rule_when_filter_excludes_now(db_session, fake_specs):
    from datetime import timedelta
    fake_specs.setup(["rsi", "macd"])
    fake_specs.state["slug_directions"] = {"rsi": "bullish", "macd": "bullish"}

    await _seed_pattern_rule_with_filter(
        db_session, [{"feature": "session", "exclude": "asia"}]
    )
    asia_now = datetime(2026, 5, 25, 2, 0, tzinfo=timezone.utc)
    await _seed_bars_at(db_session, asia_now)

    result = await paper_trader.run_paper_trader(db_session, _tick(asia_now))

    assert result["opened"] == 0
    trades = (await db_session.execute(select(Trade))).scalars().all()
    assert trades == []


@pytest.mark.asyncio
async def test_run_paper_trader_opens_when_filter_does_not_match(db_session, fake_specs):
    from datetime import timedelta
    fake_specs.setup(["rsi", "macd"])
    fake_specs.state["slug_directions"] = {"rsi": "bullish", "macd": "bullish"}

    await _seed_pattern_rule_with_filter(
        db_session, [{"feature": "session", "exclude": "asia"}]
    )
    london_now = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)
    await _seed_bars_at(db_session, london_now)

    result = await paper_trader.run_paper_trader(db_session, _tick(london_now))

    assert result["opened"] == 1

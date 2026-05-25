import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models.pattern import PaperTraderRule, Pattern
from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, OrderType, PaperMode, Trade
from schemas.market_tick import MarketTickSchema
from services import paper_trader
from services.indicators.common import IndicatorSpec
from services.paper_trader import _build_indicator_cache, run_paper_trader


@pytest.fixture(autouse=True)
def reset_paper_trader_cache():
    paper_trader.reset_cache()
    yield
    paper_trader.reset_cache()


@pytest.fixture
def fake_specs(monkeypatch):
    """Return controllable indicator specs by patching ALL_SPECS."""

    state = {"slug_directions": {}, "atr": 5.0}

    def fake_compute(slug):
        def _compute(df):
            direction = state["slug_directions"].get(slug, "neutral")
            return 1.0, direction, {}

        return _compute

    def fake_pivot_compute(df):
        return 1900.0, "neutral", {"r1": 1910.0, "r2": 1925.0, "s1": 1890.0, "s2": 1875.0}

    def fake_atr(df, length):
        import pandas as pd

        return pd.Series([state["atr"]] * len(df))

    def make_specs(slugs):
        return {slug: IndicatorSpec(slug, "momentum", fake_compute(slug)) for slug in slugs}

    fake_pivot = IndicatorSpec("pivot_std", "sr", fake_pivot_compute)

    def setup(slugs, group_overrides=None):
        registry = make_specs(slugs)
        if group_overrides:
            for slug, group in group_overrides.items():
                if slug in registry:
                    registry[slug] = IndicatorSpec(slug, group, fake_compute(slug))
        registry["pivot_std"] = fake_pivot
        monkeypatch.setattr(paper_trader, "ALL_SPECS", registry)
        monkeypatch.setattr(paper_trader, "SR_SPECS", {"pivot_std": fake_pivot})
        monkeypatch.setattr(paper_trader, "_atr", fake_atr)

    return type("F", (), {"setup": staticmethod(setup), "state": state})


async def _make_rule(session, slugs, status="active") -> PaperTraderRule:
    pattern = Pattern(
        indicator_slugs=slugs,
        timeframe="H1",
        win_rate=0.7,
        sample_count=10,
        consecutive_stable_days=3,
        status=status,
        promoted_at=datetime.now(timezone.utc),
    )
    session.add(pattern)
    await session.flush()
    rule = PaperTraderRule(pattern_id=pattern.id, status=status)
    session.add(rule)
    await session.commit()
    return rule


async def _seed_bars(session, *, count=30, base=1900.0):
    now = datetime(2026, 5, 25, 12, tzinfo=timezone.utc)
    for i in range(count):
        session.add(
            PriceBar(
                time=now - timedelta(hours=count - i),
                symbol="XAUUSD",
                timeframe=Timeframe.H1,
                open=Decimal(str(base + i * 0.1)),
                high=Decimal(str(base + i * 0.1 + 1)),
                low=Decimal(str(base + i * 0.1 - 1)),
                close=Decimal(str(base + i * 0.1 + 0.5)),
                volume=Decimal("100"),
            )
        )
    await session.commit()


def _tick(now: datetime, bid: float = 1900.0, ask: float = 1900.5) -> MarketTickSchema:
    return MarketTickSchema(
        timestamp=now, symbol="XAUUSD", bid=Decimal(str(bid)), ask=Decimal(str(ask))
    )


@pytest.mark.asyncio
async def test_load_active_rules_caches(db_session):
    rule = await _make_rule(db_session, ["rsi", "macd"])
    now = datetime.now(timezone.utc)

    snapshots1 = await paper_trader.load_active_rules(db_session, now)
    assert len(snapshots1) == 1
    assert snapshots1[0].rule_id == rule.id

    rule.status = "retired"
    await db_session.commit()

    snapshots2 = await paper_trader.load_active_rules(db_session, now)
    assert len(snapshots2) == 1, "cache should not refresh within TTL"

    paper_trader.reset_cache()
    snapshots3 = await paper_trader.load_active_rules(db_session, now)
    assert snapshots3 == []


@pytest.mark.asyncio
async def test_signal_monitor_opens_paper_trade_on_consensus(db_session, fake_specs):
    fake_specs.setup(["rsi", "macd"])
    fake_specs.state["slug_directions"] = {"rsi": "bullish", "macd": "bullish"}

    rule = await _make_rule(db_session, ["rsi", "macd"])
    await _seed_bars(db_session)

    now = datetime(2026, 5, 25, 12, tzinfo=timezone.utc)
    result = await paper_trader.run_paper_trader(db_session, _tick(now, bid=1900.0, ask=1900.5))
    assert result == {"opened": 1, "closed": 0}

    trades = (await db_session.execute(select(Trade).where(Trade.is_paper.is_(True)))).scalars().all()
    assert len(trades) == 1
    t = trades[0]
    assert t.direction == Direction.buy
    assert t.tp == Decimal("1910.00000")
    assert t.sl == Decimal("1893.00000")
    assert t.paper_mode == PaperMode.independent
    assert (t.recovery_plan or {})["paper_trader_rule_id"] == str(rule.id)

    rule_row = await db_session.get(PaperTraderRule, rule.id)
    assert rule_row.total_trades == 1


@pytest.mark.asyncio
async def test_signal_monitor_skips_when_directions_disagree(db_session, fake_specs):
    fake_specs.setup(["rsi", "macd"])
    fake_specs.state["slug_directions"] = {"rsi": "bullish", "macd": "bearish"}

    await _make_rule(db_session, ["rsi", "macd"])
    await _seed_bars(db_session)

    result = await paper_trader.run_paper_trader(
        db_session, _tick(datetime(2026, 5, 25, 12, tzinfo=timezone.utc))
    )
    assert result["opened"] == 0


@pytest.mark.asyncio
async def test_entry_guard_blocks_second_open_for_same_rule(db_session, fake_specs):
    fake_specs.setup(["rsi", "macd"])
    fake_specs.state["slug_directions"] = {"rsi": "bullish", "macd": "bullish"}

    rule = await _make_rule(db_session, ["rsi", "macd"])
    await _seed_bars(db_session)

    now = datetime(2026, 5, 25, 12, tzinfo=timezone.utc)
    await paper_trader.run_paper_trader(db_session, _tick(now))
    await paper_trader.run_paper_trader(db_session, _tick(now + timedelta(minutes=1)))

    trades = (await db_session.execute(select(Trade).where(Trade.is_paper.is_(True)))).scalars().all()
    assert len(trades) == 1


@pytest.mark.asyncio
async def test_exit_manager_closes_on_tp_and_increments_win_count(db_session, fake_specs):
    fake_specs.setup(["rsi", "macd"])
    fake_specs.state["slug_directions"] = {"rsi": "bullish", "macd": "bullish"}

    rule = await _make_rule(db_session, ["rsi", "macd"])
    await _seed_bars(db_session)

    now = datetime(2026, 5, 25, 12, tzinfo=timezone.utc)
    await paper_trader.run_paper_trader(db_session, _tick(now, bid=1900.0, ask=1900.5))

    fake_specs.state["slug_directions"] = {"rsi": "neutral", "macd": "neutral"}
    paper_trader.reset_cache()
    await paper_trader.run_paper_trader(
        db_session, _tick(now + timedelta(minutes=2), bid=1915.0, ask=1915.5)
    )

    trade = (await db_session.execute(select(Trade).where(Trade.is_paper.is_(True)))).scalar_one()
    assert trade.close_price == Decimal("1910.00000")
    assert trade.paper_exit_reason == "tp"

    rule_row = await db_session.get(PaperTraderRule, rule.id)
    assert rule_row.win_count == 1


@pytest.mark.asyncio
async def test_exit_manager_closes_on_sl(db_session, fake_specs):
    fake_specs.setup(["rsi", "macd"])
    fake_specs.state["slug_directions"] = {"rsi": "bullish", "macd": "bullish"}

    rule = await _make_rule(db_session, ["rsi", "macd"])
    await _seed_bars(db_session)

    now = datetime(2026, 5, 25, 12, tzinfo=timezone.utc)
    await paper_trader.run_paper_trader(db_session, _tick(now, bid=1900.0, ask=1900.5))

    fake_specs.state["slug_directions"] = {"rsi": "neutral", "macd": "neutral"}
    paper_trader.reset_cache()
    await paper_trader.run_paper_trader(
        db_session, _tick(now + timedelta(minutes=2), bid=1890.0, ask=1890.5)
    )

    trade = (await db_session.execute(select(Trade).where(Trade.is_paper.is_(True)))).scalar_one()
    assert trade.close_price == Decimal("1893.00000")
    assert trade.paper_exit_reason == "sl"

    rule_row = await db_session.get(PaperTraderRule, rule.id)
    assert rule_row.win_count == 0


@pytest.mark.asyncio
async def test_exit_manager_momentum_flip_closes(db_session, fake_specs):
    fake_specs.setup(["rsi", "macd"], group_overrides={"rsi": "momentum", "macd": "trend"})
    fake_specs.state["slug_directions"] = {"rsi": "bullish", "macd": "bullish"}

    rule = await _make_rule(db_session, ["rsi", "macd"])
    await _seed_bars(db_session)

    now = datetime(2026, 5, 25, 12, tzinfo=timezone.utc)
    await paper_trader.run_paper_trader(db_session, _tick(now, bid=1900.0, ask=1900.5))

    fake_specs.state["slug_directions"] = {"rsi": "bearish", "macd": "bullish"}
    paper_trader.reset_cache()
    await paper_trader.run_paper_trader(
        db_session, _tick(now + timedelta(minutes=2), bid=1902.0, ask=1902.5)
    )

    trade = (await db_session.execute(select(Trade).where(Trade.is_paper.is_(True)))).scalar_one()
    assert trade.paper_exit_reason == "momentum_flip"
    assert trade.close_price == Decimal("1902.00000")


@pytest.mark.asyncio
async def test_paper_trader_no_active_rules_is_noop(db_session, fake_specs):
    fake_specs.setup(["rsi"])
    result = await paper_trader.run_paper_trader(
        db_session, _tick(datetime(2026, 5, 25, 12, tzinfo=timezone.utc))
    )
    assert result == {"opened": 0, "closed": 0}


@pytest.mark.asyncio
async def test_paper_trades_endpoint_returns_open_and_closed(client, db_session, fake_specs):
    fake_specs.setup(["rsi", "macd"])
    fake_specs.state["slug_directions"] = {"rsi": "bullish", "macd": "bullish"}

    rule = await _make_rule(db_session, ["rsi", "macd"])
    await _seed_bars(db_session)

    now = datetime(2026, 5, 25, 12, tzinfo=timezone.utc)
    await paper_trader.run_paper_trader(db_session, _tick(now))

    resp = await client.get("/api/paper-trades")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["status"] == "open"
    assert body[0]["rule_id"] == str(rule.id)

    resp_rule = await client.get(f"/api/paper-trades?rule_id={rule.id}")
    assert resp_rule.status_code == 200
    assert len(resp_rule.json()) == 1

    resp_open = await client.get("/api/paper-trades?status=open")
    assert resp_open.status_code == 200
    assert len(resp_open.json()) == 1


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


def _bar_local(t: datetime, close: float = 1950.0, tf: Timeframe = Timeframe.H1) -> PriceBar:
    return PriceBar(
        symbol="XAUUSD",
        timeframe=tf,
        time=t,
        open=Decimal(str(close)),
        high=Decimal(str(close + 1)),
        low=Decimal(str(close - 1)),
        close=Decimal(str(close)),
        volume=Decimal("100"),
    )


async def _seed_bars_local(session, count: int = 300):
    base = datetime(2026, 5, 25, 0, 0, tzinfo=timezone.utc)
    for i in range(count):
        session.add(_bar_local(base + timedelta(hours=i), close=1950 + (i % 10)))
    await session.commit()


@pytest.mark.asyncio
async def test_shared_cache_computes_each_slug_once(session):
    await _seed_bars_local(session)
    pattern = Pattern(
        indicator_slugs=["rsi_14", "ema_50"],
        timeframe="H1",
        win_rate=0.7,
        sample_count=20,
        status="active",
    )
    session.add(pattern)
    await session.flush()
    for mode in ("strict", "basket_5k", "basket_50k"):
        session.add(PaperTraderRule(
            pattern_id=pattern.id, mode=mode, status="active",
        ))
    await session.commit()

    tick = MarketTickSchema(
        symbol="XAUUSD",
        bid=Decimal("1955.0"),
        ask=Decimal("1955.30"),
        timestamp=datetime(2026, 5, 25, 12, 5, tzinfo=timezone.utc),
        account_id=1,
    )

    call_log: list[str] = []
    real_compute = _build_indicator_cache.__globals__["_compute"]

    def spy(slug, bars):
        call_log.append(slug)
        return real_compute(slug, bars)

    with patch("services.paper_trader._compute", side_effect=spy):
        await run_paper_trader(session, tick)

    # Even with 3 rules sharing the same 2 slugs, each slug computed once
    assert call_log.count("rsi_14") == 1
    assert call_log.count("ema_50") == 1

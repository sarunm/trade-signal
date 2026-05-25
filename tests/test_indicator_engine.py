import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from models.indicator_signal import TradeIndicatorSignal
from models.price_bar import PriceBar, Timeframe
from models.trade import Direction, OrderState, Trade
from schemas.trade_event import TradeEventSchema


def _trade(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        ticket=12001,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("3300.00"),
        close_price=Decimal("3310.00"),
        is_paper=False,
    )
    defaults.update(overrides)
    return Trade(**defaults)


@pytest.mark.asyncio
async def test_indicator_registry_runs_all_registered_indicators():
    from services import indicator_engine

    original_registry = indicator_engine.REGISTRY.copy()
    indicator_engine.REGISTRY.clear()

    @indicator_engine.register("unit_test_indicator")
    def compute_unit_test_indicator(trade, bars_by_tf):
        return indicator_engine.IndicatorResult(
            slug="unit_test_indicator",
            value=1.0,
            direction="bullish",
            matched=True,
            timeframe="H1",
            metadata={"source": "test"},
        )

    try:
        results = await indicator_engine.compute_all(_trade(), {"H1": []})
    finally:
        indicator_engine.REGISTRY.clear()
        indicator_engine.REGISTRY.update(original_registry)

    assert len(results) == 1
    assert results[0].slug == "unit_test_indicator"
    assert results[0].metadata == {"source": "test"}


@pytest.mark.asyncio
async def test_indicator_signals_endpoint_returns_trade_signals(client, db_session):
    trade = _trade()
    db_session.add(trade)
    await db_session.flush()
    db_session.add(
        TradeIndicatorSignal(
            trade_id=trade.id,
            indicator_slug="unit_test_indicator",
            timeframe="H1",
            value=1.0,
            direction="bullish",
            matched=True,
            metadata={"source": "test"},
            calculated_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    response = await client.get(f"/api/indicator-signals/{trade.id}")

    assert response.status_code == 200
    data = response.json()
    assert data == [
        {
            "id": data[0]["id"],
            "trade_id": str(trade.id),
            "indicator_slug": "unit_test_indicator",
            "timeframe": "H1",
            "value": 1.0,
            "direction": "bullish",
            "matched": True,
            "metadata": {"source": "test"},
            "calculated_at": data[0]["calculated_at"],
        }
    ]


@pytest.mark.asyncio
async def test_trade_logger_schedules_indicator_compute_on_entry_only(db_session, monkeypatch):
    from services import trade_logger

    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)

        class FakeTask:
            pass

        return FakeTask()

    async def fake_recompute_trade_indicators_by_id(trade_id):
        return []

    monkeypatch.setattr(trade_logger.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(
        trade_logger,
        "recompute_trade_indicators_by_id",
        fake_recompute_trade_indicators_by_id,
    )

    close_event = TradeEventSchema(
        transaction_type="DEAL_ADD",
        ticket=12002,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("3300.00"),
        close_price=Decimal("3310.00"),
    )
    entry_event = TradeEventSchema(
        transaction_type="DEAL_ADD",
        ticket=12003,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("3300.00"),
        open_time=datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc),
    )

    await trade_logger.upsert_trade(db_session, close_event)
    assert scheduled == []

    await trade_logger.upsert_trade(db_session, entry_event)
    assert len(scheduled) == 1
    scheduled[0].close()


@pytest.mark.asyncio
async def test_recompute_fetches_bars_at_trade_open_time(db_session):
    from services import indicator_engine

    original_registry = indicator_engine.REGISTRY.copy()
    indicator_engine.REGISTRY.clear()
    open_time = datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc)
    trade = _trade(
        id=uuid.uuid4(),
        ticket=12004,
        open_time=open_time,
        close_price=None,
    )
    db_session.add(trade)
    db_session.add_all(
        [
            PriceBar(
                time=open_time - timedelta(minutes=15),
                symbol="XAUUSD",
                timeframe=Timeframe.M15,
                open=Decimal("3290.00"),
                high=Decimal("3295.00"),
                low=Decimal("3288.00"),
                close=Decimal("3292.00"),
            ),
            PriceBar(
                time=open_time,
                symbol="XAUUSD",
                timeframe=Timeframe.M15,
                open=Decimal("3300.00"),
                high=Decimal("3305.00"),
                low=Decimal("3298.00"),
                close=Decimal("3302.00"),
            ),
            PriceBar(
                time=open_time + timedelta(minutes=15),
                symbol="XAUUSD",
                timeframe=Timeframe.M15,
                open=Decimal("3310.00"),
                high=Decimal("3315.00"),
                low=Decimal("3308.00"),
                close=Decimal("3312.00"),
            ),
        ]
    )
    await db_session.commit()

    @indicator_engine.register("entry_anchor")
    def compute_entry_anchor(trade, bars_by_tf):
        bars = bars_by_tf["M15"]
        return indicator_engine.IndicatorResult(
            slug="entry_anchor",
            value=float(bars[-1].close),
            direction="bullish",
            matched=True,
            timeframe="M15",
            metadata={"bar_count": len(bars), "last_bar_time": bars[-1].time.isoformat()},
        )

    try:
        await indicator_engine.recompute_trade_indicators(db_session, trade)
        await db_session.commit()
    finally:
        indicator_engine.REGISTRY.clear()
        indicator_engine.REGISTRY.update(original_registry)

    signals = await db_session.execute(
        indicator_engine.select_trade_indicator_signals(trade.id)
    )
    signal = signals.scalars().one()
    assert signal.value == 3302.0
    assert signal.signal_metadata["bar_count"] == 2
    assert signal.signal_metadata["last_bar_time"] == open_time.replace(tzinfo=None).isoformat()


@pytest.mark.asyncio
async def test_recompute_replaces_existing_indicator_signals(db_session):
    from services import indicator_engine

    original_registry = indicator_engine.REGISTRY.copy()
    indicator_engine.REGISTRY.clear()
    trade = _trade(id=uuid.uuid4(), ticket=12005, close_price=None)
    db_session.add(trade)
    await db_session.flush()
    db_session.add(
        TradeIndicatorSignal(
            trade_id=trade.id,
            indicator_slug="old_signal",
            timeframe="H1",
            value=0.0,
            direction="bearish",
            matched=False,
            metadata={"old": True},
            calculated_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    @indicator_engine.register("new_signal")
    def compute_new_signal(trade, bars_by_tf):
        return indicator_engine.IndicatorResult(
            slug="new_signal",
            value=1.0,
            direction="bullish",
            matched=True,
            timeframe="H1",
            metadata={"new": True},
        )

    try:
        await indicator_engine.recompute_trade_indicators(db_session, trade)
        await db_session.commit()
    finally:
        indicator_engine.REGISTRY.clear()
        indicator_engine.REGISTRY.update(original_registry)

    signals = await db_session.execute(
        indicator_engine.select_trade_indicator_signals(trade.id)
    )
    rows = signals.scalars().all()
    assert len(rows) == 1
    assert rows[0].indicator_slug == "new_signal"
    assert rows[0].signal_metadata == {"new": True}

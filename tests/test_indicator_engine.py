import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from models.indicator_signal import TradeIndicatorSignal
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
async def test_trade_logger_schedules_indicator_compute_on_close(db_session, monkeypatch):
    from services import trade_logger

    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)

        class FakeTask:
            pass

        return FakeTask()

    async def fake_compute_all(trade, bars_by_tf):
        return []

    monkeypatch.setattr(trade_logger.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(trade_logger, "compute_all", fake_compute_all)

    event = TradeEventSchema(
        transaction_type="DEAL_ADD",
        ticket=12002,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("3300.00"),
        close_price=Decimal("3310.00"),
    )

    await trade_logger.upsert_trade(db_session, event)

    assert len(scheduled) == 1
    scheduled[0].close()

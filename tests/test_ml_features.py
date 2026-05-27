from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from ml.features import extract_trade_features
from models.trade import Direction, OrderState, Trade
from models.indicator_signal import TradeIndicatorSignal


@pytest.mark.asyncio
async def test_extract_trade_features_basic_buy(db_session):
    trade = Trade(
        id=uuid4(),
        ticket=999001,
        symbol="GOLD#",
        direction=Direction.buy,
        order_state=OrderState.filled,
        is_paper=False,
        open_time=datetime(2026, 5, 27, 9, 30, tzinfo=timezone.utc),
        open_price=Decimal("4500.00"),
        volume=Decimal("0.10"),
        entry_score=72,
        near_fib_level="R1",
        profit=Decimal("150.00"),
    )
    db_session.add(trade)
    await db_session.flush()
    db_session.add_all([
        TradeIndicatorSignal(
            id=uuid4(), trade_id=trade.id,
            indicator_slug="ema_cross", timeframe="H1",
            value=1.0, direction="bull", matched=True, metadata={},
            calculated_at=trade.open_time,
        ),
        TradeIndicatorSignal(
            id=uuid4(), trade_id=trade.id,
            indicator_slug="rsi", timeframe="H1",
            value=58.0, direction=None, matched=False, metadata={},
            calculated_at=trade.open_time,
        ),
    ])
    await db_session.commit()

    feats = await extract_trade_features(db_session, trade)
    assert feats["entry_score"] == 72
    assert feats["direction_buy"] == 1
    assert feats["near_fib_R1"] == 1
    assert feats["near_fib_S1"] == 0
    assert feats["hour_of_day_utc"] == 9
    assert feats["day_of_week"] in range(0, 7)
    assert feats["signal_match_count"] == 1
    assert feats["signal_density"] == pytest.approx(0.5)
    assert feats["rsi_value"] == 58.0


@pytest.mark.asyncio
async def test_extract_trade_features_handles_nulls(db_session):
    trade = Trade(
        id=uuid4(), ticket=999002, symbol="GOLD#",
        direction=Direction.sell, order_state=OrderState.filled, is_paper=False,
        open_time=datetime(2026, 5, 27, 0, 0, tzinfo=timezone.utc),
        open_price=Decimal("4500"), volume=Decimal("0.1"),
        entry_score=None, near_fib_level=None, profit=Decimal("-50"),
    )
    db_session.add(trade)
    await db_session.commit()

    feats = await extract_trade_features(db_session, trade)
    assert feats["entry_score"] == 0
    assert feats["near_fib_none"] == 1
    assert feats["direction_buy"] == 0
    assert feats["signal_match_count"] == 0
    assert feats["signal_density"] == 0.0
    assert feats["rsi_value"] == 0.0

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import select

from models.alert import Alert
from models.insight import Insight
from models.price_bar import PriceBar, Timeframe
from models.trade import Trade, Direction, OrderState, OrderType

# bullish pin bar OHLCV: lower_wick=5.0, body=0.5, range=6.0
PIN_BAR_TICK = {
    "timestamp": "2026-05-18T10:00:00Z",
    "symbol": "GOLD#",
    "account": {
        "equity": 10000, "balance": 10000,
        "margin": 0, "free_margin": 10000, "floating_pl": 0,
    },
    "bars": {
        "H1": {"open": 1920.0, "high": 1921.0, "low": 1915.0, "close": 1920.5, "volume": 100},
    },
}


@pytest.mark.asyncio
async def test_price_tick_creates_pattern_alert_for_pin_bar(client, db_session):
    response = await client.post("/api/price-tick", json=PIN_BAR_TICK)
    assert response.status_code == 200

    result = await db_session.execute(select(Alert).where(Alert.type == "pattern_alert"))
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert alerts[0].trigger_data["pattern"] == "pin_bar"
    assert alerts[0].trigger_data["direction"] == "bullish"


@pytest.mark.asyncio
async def test_pattern_win_rate_insight_created(db_session):
    from services.insight_engine import run_insight_engine

    # Insert 10 winning trades each with a matching H1 pin bar
    for i in range(10):
        t = datetime(2026, 5, i + 1, 10, 0, tzinfo=timezone.utc)
        db_session.add(PriceBar(
            time=t, symbol="GOLD#", timeframe=Timeframe.H1,
            open=Decimal("1920.0"), high=Decimal("1921.0"),
            low=Decimal("1915.0"), close=Decimal("1920.5"),
        ))
        db_session.add(Trade(
            id=uuid.uuid4(), ticket=1000 + i, symbol="GOLD#",
            direction=Direction.buy, order_type=OrderType.market,
            order_state=OrderState.filled, is_paper=False,
            open_price=Decimal("1920.0"), close_price=Decimal("1921.0"),
            profit=Decimal("10.0"),
            open_time=t, close_time=t + timedelta(hours=2),
        ))
    await db_session.commit()

    await run_insight_engine(db_session)

    result = await db_session.execute(
        select(Insight).where(Insight.type == "pattern_win_rate", Insight.is_active == True)
    )
    insights = result.scalars().all()
    assert len(insights) == 1
    assert insights[0].confidence >= 0.6
    assert insights[0].sample_size == 10
    assert "pin_bar" in insights[0].description

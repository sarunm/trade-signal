import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from models.price_bar import PriceBar
from models.trade import Direction, OrderState, PaperMode, Trade


MARKET_TICK = {
    "timestamp": "2026-05-18T10:05:00Z",
    "symbol": "XAUUSD",
    "bid": 1960.10,
    "ask": 1960.30,
}


@pytest.mark.asyncio
async def test_market_tick_closes_matching_paper_trade_without_storing_tick(client, db_session):
    paper = Trade(
        id=uuid.uuid4(),
        ticket=8001,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("1950.00"),
        volume=Decimal("0.10"),
        tp=Decimal("1960.00"),
        sl=Decimal("1945.00"),
        open_time=datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
        is_paper=True,
        paper_mode=PaperMode.mirror,
    )
    db_session.add(paper)
    await db_session.commit()

    response = await client.post("/api/market-tick", json=MARKET_TICK)

    assert response.status_code == 200
    assert response.json()["closed_paper_trades"] == 1
    assert paper.close_price == Decimal("1960.00")
    assert paper.close_time == datetime(2026, 5, 18, 10, 5, tzinfo=timezone.utc)
    assert paper.paper_exit_reason == "tp"
    bars = (await db_session.execute(select(PriceBar))).scalars().all()
    assert bars == []


@pytest.mark.asyncio
async def test_market_tick_rejects_crossed_market(client):
    response = await client.post(
        "/api/market-tick",
        json={**MARKET_TICK, "bid": 1960.50, "ask": 1960.30},
    )

    assert response.status_code == 422

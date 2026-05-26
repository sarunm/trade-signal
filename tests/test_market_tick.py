import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from models.price_bar import PriceBar, Timeframe
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
        paper_mode=PaperMode.independent,
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


@pytest.mark.asyncio
async def test_market_tick_closes_open_mirror_via_pivot_tp(
    client, db_session, monkeypatch
):
    """Regression guard: /api/market-tick must invoke evaluate_mirror_exits and
    surface the count via response.closed_mirror. If someone removes the mirror
    call from market_tick.py this test fails."""
    monkeypatch.setattr(
        "services.mirror_exit_manager._momentum_weakening", lambda *a, **k: True
    )

    tick_time = datetime(2026, 5, 18, 10, 5, tzinfo=timezone.utc)
    db_session.add(PriceBar(
        symbol="XAUUSD", timeframe=Timeframe.D,
        time=tick_time - timedelta(days=2),
        open=Decimal("1900"), high=Decimal("1920"),
        low=Decimal("1880"), close=Decimal("1910"), volume=Decimal("100"),
    ))
    db_session.add(PriceBar(
        symbol="XAUUSD", timeframe=Timeframe.D,
        time=tick_time - timedelta(days=1),
        open=Decimal("1910"), high=Decimal("1955"),
        low=Decimal("1905"), close=Decimal("1950"), volume=Decimal("100"),
    ))
    h1_anchor = tick_time - timedelta(hours=250)
    for i in range(250):
        db_session.add(PriceBar(
            symbol="XAUUSD", timeframe=Timeframe.H1,
            time=h1_anchor + timedelta(hours=i),
            open=Decimal("1950"), high=Decimal("1955"),
            low=Decimal("1948"),
            close=Decimal("1950") + Decimal("0.5") * (i % 5),
            volume=Decimal("100"),
        ))

    mirror = Trade(
        id=uuid.uuid4(),
        ticket=9001,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("1920.00"),
        volume=Decimal("0.10"),
        open_time=tick_time - timedelta(hours=1),
        is_paper=True,
        paper_mode=PaperMode.mirror,
        paper_exit_strategy="rule_driven",
    )
    db_session.add(mirror)
    await db_session.commit()

    # R1 = 2*PP - L = 2*((1955+1905+1950)/3) - 1905 ≈ 1968.33
    response = await client.post("/api/market-tick", json={
        "timestamp": tick_time.isoformat().replace("+00:00", "Z"),
        "symbol": "XAUUSD",
        "bid": 1968.50,
        "ask": 1968.55,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["closed_mirror"] == 1
    assert body["closed_paper_trades"] >= 1
    await db_session.refresh(mirror)
    assert mirror.paper_exit_reason == "tp_pivot"
    assert mirror.close_time is not None

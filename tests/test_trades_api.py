import pytest
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from models.trade import Trade, Direction, OrderState, OrderType


def make_trade(ticket, is_paper=False, close_price=None, profit=None):
    return Trade(
        id=uuid.uuid4(),
        ticket=ticket,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_type=OrderType.market,
        order_state=OrderState.filled,
        open_price=Decimal("1920.00000"),
        close_price=close_price,
        profit=profit,
        volume=Decimal("0.10"),
        is_paper=is_paper,
        open_time=datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
        close_time=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc) if close_price else None,
    )


@pytest.mark.asyncio
async def test_list_open_trades(client, db_session):
    db_session.add(make_trade(1001))
    db_session.add(make_trade(1002, close_price=Decimal("1930.00000"), profit=Decimal("100.00")))
    await db_session.commit()

    response = await client.get("/api/trades?state=open")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticket"] == 1001
    assert data[0]["close_price"] is None


@pytest.mark.asyncio
async def test_list_closed_trades(client, db_session):
    db_session.add(make_trade(1001))
    db_session.add(make_trade(1002, close_price=Decimal("1930.00000"), profit=Decimal("100.00")))
    await db_session.commit()

    response = await client.get("/api/trades?state=closed")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticket"] == 1002


@pytest.mark.asyncio
async def test_list_trades_returns_both_real_and_paper(client, db_session):
    db_session.add(make_trade(1001, is_paper=False))
    paper = make_trade(1001, is_paper=True)
    paper.paper_exit_strategy = "tp:session_direction_avg;sl:direction_avg"
    paper.paper_exit_reason = "tp"
    db_session.add(paper)
    await db_session.commit()

    response = await client.get("/api/trades?state=open")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    paper_row = next(row for row in data if row["is_paper"])
    assert paper_row["paper_exit_strategy"] == "tp:session_direction_avg;sl:direction_avg"
    assert paper_row["paper_exit_reason"] == "tp"


@pytest.mark.asyncio
async def test_list_closed_trades_limit(client, db_session):
    for i in range(5):
        db_session.add(make_trade(2000 + i, close_price=Decimal("1930.00000"), profit=Decimal("10.00")))
    await db_session.commit()

    response = await client.get("/api/trades?state=closed&limit=3")
    assert response.status_code == 200
    assert len(response.json()) == 3


@pytest.mark.asyncio
async def test_invalid_state_returns_422(client):
    response = await client.get("/api/trades?state=invalid")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_trade_response_includes_entry_context_fields(client, db_session):
    trade = Trade(
        id=uuid.uuid4(),
        ticket=1001,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("2000.00"),
        open_time=datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc),
        is_paper=False,
        setup_pattern="double_bottom",
        trade_bias="bullish",
        near_fib_level="S0.235",
        fib_distance_pts=Decimal("3.50"),
        entry_candle="pin_bar_bullish",
        entry_candle_tf="H1",
        is_rescue=False,
    )
    db_session.add(trade)
    await db_session.commit()

    resp = await client.get("/api/trades?state=open")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    t = data[0]
    assert t["setup_pattern"] == "double_bottom"
    assert t["trade_bias"] == "bullish"
    assert t["near_fib_level"] == "S0.235"
    assert float(t["fib_distance_pts"]) == pytest.approx(3.5)
    assert t["entry_candle"] == "pin_bar_bullish"
    assert t["entry_candle_tf"] == "H1"
    assert t["is_rescue"] is False
    assert t["post_close_run_pts"] is None


@pytest.mark.asyncio
async def test_patch_tag_updates_setup_pattern(client, db_session):
    trade = Trade(
        id=uuid.uuid4(),
        ticket=3001,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("2000.00"),
        open_time=datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc),
        is_paper=False,
    )
    db_session.add(trade)
    await db_session.commit()

    resp = await client.patch(
        "/api/trades/3001/tag",
        json={"setup_pattern": "double_bottom", "trade_bias": "bullish"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["setup_pattern"] == "double_bottom"
    assert data["trade_bias"] == "bullish"


@pytest.mark.asyncio
async def test_patch_tag_rejects_invalid_pattern(client, db_session):
    trade = Trade(
        id=uuid.uuid4(),
        ticket=3002,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("2000.00"),
        open_time=datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc),
        is_paper=False,
    )
    db_session.add(trade)
    await db_session.commit()

    resp = await client.patch(
        "/api/trades/3002/tag",
        json={"setup_pattern": "not_a_real_pattern"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_tag_returns_404_for_unknown_ticket(client, db_session):
    resp = await client.patch(
        "/api/trades/99999/tag",
        json={"setup_pattern": "double_bottom"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_trades_respects_offset(client, db_session):
    for i in range(5):
        trade = Trade(
            id=uuid.uuid4(),
            ticket=5000 + i,
            symbol="XAUUSD",
            direction=Direction.buy,
            order_state=OrderState.filled,
            open_price=Decimal("2000.00"),
            close_price=Decimal("2010.00"),
            open_time=datetime(2026, 5, 19, i, 0, tzinfo=timezone.utc),
            close_time=datetime(2026, 5, 19, i, 1, tzinfo=timezone.utc),
            profit=Decimal("100.00"),
            is_paper=False,
        )
        db_session.add(trade)
    await db_session.commit()

    resp_all = await client.get("/api/trades?state=closed&limit=10&offset=0")
    resp_offset = await client.get("/api/trades?state=closed&limit=10&offset=2")
    assert resp_all.status_code == 200
    assert resp_offset.status_code == 200
    assert len(resp_all.json()) == 5
    assert len(resp_offset.json()) == 3

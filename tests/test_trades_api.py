import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from models.account_snapshot import AccountSnapshot
from models.trade import Direction, OrderState, OrderType, Trade
from sqlalchemy import select


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
        close_time=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
        if close_price
        else None,
    )


@pytest.mark.asyncio
async def test_list_open_trades(client, db_session):
    db_session.add(make_trade(1001))
    db_session.add(
        make_trade(1002, close_price=Decimal("1930.00000"), profit=Decimal("100.00"))
    )
    await db_session.commit()

    response = await client.get("/api/trades?state=open")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticket"] == 1001
    assert data[0]["close_price"] is None


@pytest.mark.asyncio
async def test_list_open_trades_excludes_expired_orders(client, db_session):
    open_trade = make_trade(1001)
    expired = make_trade(1002)
    expired.order_state = OrderState.expired
    expired.open_price = None
    db_session.add(open_trade)
    db_session.add(expired)
    await db_session.commit()

    response = await client.get("/api/trades?state=open")

    assert response.status_code == 200
    data = response.json()
    assert [row["ticket"] for row in data] == [1001]


@pytest.mark.asyncio
async def test_list_trades_account_scope_keeps_matching_paper_pair(client, db_session):
    db_session.add(
        AccountSnapshot(
            timestamp=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
            equity=Decimal("10000.00"),
            balance=Decimal("10000.00"),
            margin=Decimal("0.00"),
            free_margin=Decimal("10000.00"),
            floating_pl=Decimal("0.00"),
            account_id=335297575,
        )
    )
    real = make_trade(1001, is_paper=False)
    real.account_id = 335297575
    paper = make_trade(1001, is_paper=True)
    paper.account_id = 335297575
    other = make_trade(1002, is_paper=False)
    other.account_id = 999999
    db_session.add_all([real, paper, other])
    await db_session.commit()

    response = await client.get("/api/trades?state=open")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert {row["is_paper"] for row in data} == {False, True}
    assert {row["ticket"] for row in data} == {1001}
    assert all(row["open_price"] is not None for row in data)


@pytest.mark.asyncio
async def test_list_closed_trades(client, db_session):
    db_session.add(make_trade(1001))
    db_session.add(
        make_trade(1002, close_price=Decimal("1930.00000"), profit=Decimal("100.00"))
    )
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
    assert (
        paper_row["paper_exit_strategy"] == "tp:session_direction_avg;sl:direction_avg"
    )
    assert paper_row["paper_exit_reason"] == "tp"


@pytest.mark.asyncio
async def test_list_closed_trades_limit(client, db_session):
    for i in range(5):
        db_session.add(
            make_trade(
                2000 + i, close_price=Decimal("1930.00000"), profit=Decimal("10.00")
            )
        )
    await db_session.commit()

    response = await client.get("/api/trades?state=closed&limit=3")
    assert response.status_code == 200
    assert len(response.json()) == 3


@pytest.mark.asyncio
async def test_invalid_state_returns_422(client):
    response = await client.get("/api/trades?state=invalid")
    assert response.status_code == 422


def _pending(ticket: int, order_type: OrderType, pending_price: str, direction: Direction = Direction.buy) -> Trade:
    return Trade(
        id=uuid.uuid4(),
        ticket=ticket,
        symbol="GOLD#",
        direction=direction,
        order_type=order_type,
        order_state=OrderState.pending,
        open_price=None,
        pending_price=Decimal(pending_price),
        volume=Decimal("0.10"),
        is_paper=False,
        open_time=datetime(2026, 5, 27, 10, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_list_pending_returns_all_pending_types(client, db_session):
    db_session.add_all([
        _pending(5001, OrderType.buy_limit, "4500.00"),
        _pending(5002, OrderType.sell_limit, "4600.00", direction=Direction.sell),
        _pending(5003, OrderType.buy_stop, "4650.00"),
        _pending(5004, OrderType.sell_stop, "4400.00", direction=Direction.sell),
    ])
    db_session.add(make_trade(1001))
    await db_session.commit()

    response = await client.get("/api/trades?state=pending")
    assert response.status_code == 200
    data = response.json()
    tickets = {row["ticket"] for row in data}
    assert tickets == {5001, 5002, 5003, 5004}
    for row in data:
        assert row["order_state"] == "pending"
        assert row["pending_price"] is not None
        assert row["close_price"] is None


@pytest.mark.asyncio
async def test_list_pending_excludes_filled_and_cancelled(client, db_session):
    pending = _pending(5001, OrderType.buy_limit, "4500.00")
    cancelled = _pending(5002, OrderType.buy_limit, "4400.00")
    cancelled.order_state = OrderState.cancelled
    cancelled.close_time = datetime(2026, 5, 27, 11, 0, tzinfo=timezone.utc)
    cancelled.close_price = Decimal("4400.00")
    db_session.add_all([pending, cancelled, make_trade(1001)])
    await db_session.commit()

    response = await client.get("/api/trades?state=pending")
    assert response.status_code == 200
    tickets = {row["ticket"] for row in response.json()}
    assert tickets == {5001}


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


@pytest.mark.asyncio
async def test_get_pnl_history_returns_cumulative_real_closed_trades_sorted(
    client, db_session
):
    db_session.add_all(
        [
            make_trade(
                6001,
                close_price=Decimal("1930.00000"),
                profit=Decimal("100.50"),
            ),
            make_trade(
                6002,
                close_price=Decimal("1910.00000"),
                profit=Decimal("-25.25"),
            ),
            make_trade(
                6003,
                close_price=Decimal("1940.00000"),
                profit=Decimal("10.00"),
            ),
        ]
    )
    await db_session.flush()
    trades = await db_session.execute(
        select(Trade).where(Trade.ticket.in_([6001, 6002, 6003]))
    )
    rows = {trade.ticket: trade for trade in trades.scalars().all()}
    rows[6001].close_time = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
    rows[6002].close_time = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc)
    rows[6003].close_time = datetime(2026, 5, 19, 14, 0, tzinfo=timezone.utc)
    await db_session.commit()

    response = await client.get("/api/trades/pnl-history?days=30")

    assert response.status_code == 200
    assert response.json() == [
        {"date": "2026-05-18", "cumulative_pnl": 100.5},
        {"date": "2026-05-19", "cumulative_pnl": 85.25},
    ]


@pytest.mark.asyncio
async def test_get_pnl_history_excludes_paper_open_and_null_profit_trades(
    client, db_session
):
    closed_real = make_trade(
        6101, close_price=Decimal("1930.00000"), profit=Decimal("80.00")
    )
    paper = make_trade(
        6102, is_paper=True, close_price=Decimal("1930.00000"), profit=Decimal("999.00")
    )
    open_real = make_trade(6103, profit=Decimal("50.00"))
    null_profit = make_trade(6104, close_price=Decimal("1930.00000"))
    db_session.add_all([closed_real, paper, open_real, null_profit])
    await db_session.commit()

    response = await client.get("/api/trades/pnl-history?days=30")

    assert response.status_code == 200
    assert response.json() == [{"date": "2026-05-18", "cumulative_pnl": 80.0}]


@pytest.mark.asyncio
async def test_get_pnl_history_uses_today_anchor_not_latest_trade(client, db_session):
    old_trade = make_trade(
        6201, close_price=Decimal("1930.00000"), profit=Decimal("80.00")
    )
    old_trade.close_time = datetime.now(timezone.utc) - timedelta(days=60)
    db_session.add(old_trade)
    await db_session.commit()

    response = await client.get("/api/trades/pnl-history?days=30")

    assert response.status_code == 200
    assert response.json() == []

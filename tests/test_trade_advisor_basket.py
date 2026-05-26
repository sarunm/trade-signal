from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from models.account_snapshot import AccountSnapshot
from models.price_bar import PriceBar
from models.trade import Direction, OrderState, Trade

_BKK = timezone(timedelta(hours=7))


def _t(ticket, direction, vol, entry):
    return Trade(
        id=uuid4(), ticket=ticket, symbol="XAUUSD", direction=direction,
        order_state=OrderState.filled, is_paper=False,
        open_time=datetime.now(timezone.utc),
        open_price=Decimal(str(entry)),
        volume=Decimal(str(vol)),
    )


@pytest.mark.asyncio
async def test_basket_three_buys_uses_weighted_avg(client, db_session):
    db_session.add_all([
        _t(7001, Direction.buy, "0.10", "1955.00"),
        _t(7002, Direction.buy, "0.10", "1957.00"),
        _t(7003, Direction.buy, "0.10", "1959.00"),
    ])
    db_session.add(AccountSnapshot(
        timestamp=datetime.now(timezone.utc),
        equity=Decimal("100000"), balance=Decimal("100000"),
        margin=Decimal("3000"), free_margin=Decimal("97000"),
        floating_pl=Decimal("0"),
    ))
    await db_session.commit()

    res = await client.get("/api/trade-advisor")
    body = res.json()
    assert "basket" in body
    b = body["basket"]
    assert b["direction"] == "buy"
    assert b["order_count"] == 3
    assert Decimal(str(b["lot_total"])) == Decimal("0.30")
    assert Decimal(str(b["avg_entry"])) == Decimal("1957.00")


@pytest.mark.asyncio
async def test_basket_no_open_returns_flat(client, db_session):
    res = await client.get("/api/trade-advisor")
    body = res.json()
    b = body["basket"]
    assert b["direction"] == "flat"
    assert b["lot_total"] == 0
    assert b["order_count"] == 0
    assert b["avg_entry"] is None


@pytest.mark.asyncio
async def test_basket_mixed_direction_nets_by_lot(client, db_session):
    db_session.add_all([
        _t(8001, Direction.buy, "0.20", "1955.00"),
        _t(8002, Direction.sell, "0.05", "1958.00"),
    ])
    db_session.add(AccountSnapshot(
        timestamp=datetime.now(timezone.utc),
        equity=Decimal("100000"), balance=Decimal("100000"),
        margin=Decimal("3000"), free_margin=Decimal("97000"),
        floating_pl=Decimal("0"),
    ))
    await db_session.commit()

    res = await client.get("/api/trade-advisor")
    body = res.json()
    b = body["basket"]
    assert b["direction"] == "buy"
    assert Decimal(str(b["lot_total"])) == Decimal("0.15")
    assert b["order_count"] == 2


@pytest.mark.asyncio
async def test_basket_uses_latest_m5_close_for_current_and_net_float(client, db_session):
    db_session.add_all([
        _t(9001, Direction.buy, "0.10", "1955.00"),
        _t(9002, Direction.buy, "0.10", "1957.00"),
    ])
    db_session.add(PriceBar(
        time=datetime.now(timezone.utc),
        symbol="XAUUSD", timeframe="M5",
        open=Decimal("1959"), high=Decimal("1960"),
        low=Decimal("1958"), close=Decimal("1960.00"),
        volume=Decimal("100"),
    ))
    db_session.add(AccountSnapshot(
        timestamp=datetime.now(timezone.utc),
        equity=Decimal("100000"), balance=Decimal("100000"),
        margin=Decimal("3000"), free_margin=Decimal("97000"),
        floating_pl=Decimal("0"),
    ))
    await db_session.commit()

    res = await client.get("/api/trade-advisor")
    b = res.json()["basket"]
    assert Decimal(str(b["current"])) == Decimal("1960.00")
    assert Decimal(str(b["basket_be"])) == Decimal("1956.00")
    assert Decimal(str(b["net_float"])) > 0

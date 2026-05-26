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


@pytest.mark.asyncio
async def test_basket_ruin_safe_tier(client, db_session, monkeypatch):
    monkeypatch.setenv("RUIN_STOP_OUT_PCT", "50")
    db_session.add(_t(9101, Direction.buy, "0.10", "1955.00"))
    db_session.add(PriceBar(
        time=datetime.now(timezone.utc), symbol="XAUUSD", timeframe="M5",
        open=Decimal("1958"), high=Decimal("1958"),
        low=Decimal("1958"), close=Decimal("1958.00"),
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
    ruin = res.json()["basket"]["ruin"]
    assert ruin["tier"] == "safe"
    assert Decimal(str(ruin["pct_buffer"])) > Decimal("50")
    assert Decimal(str(ruin["pts"])) < 0
    assert Decimal(str(ruin["baht_buffer"])) < 0


@pytest.mark.asyncio
async def test_basket_ruin_danger_tier_when_buffer_low(client, db_session, monkeypatch):
    monkeypatch.setenv("RUIN_STOP_OUT_PCT", "50")
    db_session.add(_t(9201, Direction.buy, "1.00", "1955.00"))
    db_session.add(PriceBar(
        time=datetime.now(timezone.utc), symbol="XAUUSD", timeframe="M5",
        open=Decimal("1955"), high=Decimal("1955"),
        low=Decimal("1955"), close=Decimal("1955.00"),
        volume=Decimal("100"),
    ))
    db_session.add(AccountSnapshot(
        timestamp=datetime.now(timezone.utc),
        equity=Decimal("1700"), balance=Decimal("1700"),
        margin=Decimal("3000"), free_margin=Decimal("-1300"),
        floating_pl=Decimal("0"),
    ))
    await db_session.commit()

    res = await client.get("/api/trade-advisor")
    ruin = res.json()["basket"]["ruin"]
    assert ruin["tier"] == "danger"


@pytest.mark.asyncio
async def test_basket_ruin_null_when_no_snapshot(client, db_session):
    db_session.add(_t(9301, Direction.buy, "0.10", "1955.00"))
    db_session.add(PriceBar(
        time=datetime.now(timezone.utc), symbol="XAUUSD", timeframe="M5",
        open=Decimal("1958"), high=Decimal("1958"),
        low=Decimal("1958"), close=Decimal("1958.00"),
        volume=Decimal("100"),
    ))
    await db_session.commit()

    res = await client.get("/api/trade-advisor")
    assert res.json()["basket"]["ruin"] is None


@pytest.mark.asyncio
async def test_basket_tp_targets_and_zones_use_deepest_trade(client, db_session):
    plan = {
        "entry_price": 1955.0,
        "tp": [
            {"label": "BE", "price": 1956.85, "pts": 18.5},
            {"label": "R1", "price": 1965.10, "pts": 101.0},
            {"label": "R2", "price": 1972.50, "pts": 175.0},
        ],
        "add": [
            {"label": "S1", "price": 1948.30, "pts": -67.0},
            {"label": "S2", "price": 1940.10, "pts": -149.0},
        ],
        "cut": {"label": "S3", "price": 1928.50, "pts": -265.0},
    }
    deepest = _t(9401, Direction.buy, "0.10", "1955.00")
    deepest.recovery_plan = plan
    db_session.add(deepest)
    db_session.add(_t(9402, Direction.buy, "0.10", "1958.00"))
    db_session.add(PriceBar(
        time=datetime.now(timezone.utc), symbol="XAUUSD", timeframe="M5",
        open=Decimal("1959"), high=Decimal("1959"),
        low=Decimal("1959"), close=Decimal("1959.00"),
        volume=Decimal("100"),
    ))
    db_session.add(AccountSnapshot(
        timestamp=datetime.now(timezone.utc),
        equity=Decimal("100000"), balance=Decimal("100000"),
        margin=Decimal("3000"), free_margin=Decimal("97000"),
        floating_pl=Decimal("0"),
    ))
    await db_session.commit()

    b = (await client.get("/api/trade-advisor")).json()["basket"]
    labels = [tp["label"] for tp in b["tp_targets"]]
    assert labels == ["R2", "R1", "BE"]
    assert [z["label"] for z in b["add_zones"]] == ["S1", "S2"]
    assert b["cut"]["label"] == "S3"


@pytest.mark.asyncio
async def test_basket_pnl_summary_buckets_today_week_month(client, db_session, monkeypatch):
    today_close = datetime(2026, 5, 26, 12, tzinfo=_BKK).astimezone(timezone.utc)
    week_close = datetime(2026, 5, 22, 12, tzinfo=_BKK).astimezone(timezone.utc)
    month_close = datetime(2026, 5, 5, 12, tzinfo=_BKK).astimezone(timezone.utc)
    older = datetime(2026, 4, 5, 12, tzinfo=_BKK).astimezone(timezone.utc)

    db_session.add_all([
        Trade(id=uuid4(), ticket=10001, symbol="XAUUSD", direction=Direction.buy,
              order_state=OrderState.filled, is_paper=False,
              open_time=today_close, close_time=today_close,
              open_price=Decimal("1955"), close_price=Decimal("1960"),
              volume=Decimal("0.10"), profit=Decimal("420.00")),
        Trade(id=uuid4(), ticket=10002, symbol="XAUUSD", direction=Direction.buy,
              order_state=OrderState.filled, is_paper=False,
              open_time=week_close, close_time=week_close,
              open_price=Decimal("1955"), close_price=Decimal("1960"),
              volume=Decimal("0.10"), profit=Decimal("1430.00")),
        Trade(id=uuid4(), ticket=10003, symbol="XAUUSD", direction=Direction.buy,
              order_state=OrderState.filled, is_paper=False,
              open_time=month_close, close_time=month_close,
              open_price=Decimal("1955"), close_price=Decimal("1960"),
              volume=Decimal("0.10"), profit=Decimal("2380.00")),
        Trade(id=uuid4(), ticket=10004, symbol="XAUUSD", direction=Direction.buy,
              order_state=OrderState.filled, is_paper=False,
              open_time=older, close_time=older,
              open_price=Decimal("1955"), close_price=Decimal("1960"),
              volume=Decimal("0.10"), profit=Decimal("999.00")),
    ])
    db_session.add(AccountSnapshot(
        timestamp=today_close,
        equity=Decimal("100000"), balance=Decimal("100000"),
        margin=Decimal("0"), free_margin=Decimal("100000"),
        floating_pl=Decimal("0"),
    ))
    await db_session.commit()

    monkeypatch.setattr(
        "routers.trade_advisor._today_in_bkk",
        lambda: datetime(2026, 5, 26, tzinfo=_BKK).date(),
    )

    b = (await client.get("/api/trade-advisor")).json()["basket"]
    s = b["pnl_summary"]
    assert Decimal(str(s["today"]["baht"])) == Decimal("420.00")
    assert Decimal(str(s["week"]["baht"])) == Decimal("1850.00")
    assert Decimal(str(s["month"]["baht"])) == Decimal("4230.00")

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from models.trade import Direction, OrderState, Trade

_BKK = timezone(timedelta(hours=7))


def _bkk(year, month, day, hour=12):
    return datetime(year, month, day, hour, tzinfo=_BKK).astimezone(timezone.utc)


@pytest.mark.asyncio
async def test_pnl_history_daily_groups_by_bkk_date(client, db_session):
    db_session.add_all([
        Trade(
            id=uuid4(), ticket=1001, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 26, 9), close_time=_bkk(2026, 5, 26, 15),
            open_price=Decimal("1955"), close_price=Decimal("1960"),
            volume=Decimal("0.10"), profit=Decimal("420.00"),
        ),
        Trade(
            id=uuid4(), ticket=1002, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 26, 16), close_time=_bkk(2026, 5, 26, 18),
            open_price=Decimal("1962"), close_price=Decimal("1965"),
            volume=Decimal("0.05"), profit=Decimal("150.00"),
        ),
        Trade(
            id=uuid4(), ticket=1003, symbol="XAUUSD", direction=Direction.sell,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 25, 10), close_time=_bkk(2026, 5, 25, 14),
            open_price=Decimal("1958"), close_price=Decimal("1960"),
            volume=Decimal("0.05"), profit=Decimal("-100.00"),
        ),
    ])
    await db_session.commit()

    res = await client.get("/api/pnl-history?granularity=daily&page=1&page_size=20")
    assert res.status_code == 200
    body = res.json()

    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total_count"] == 2
    assert body["total_pages"] == 1
    assert len(body["items"]) == 2

    first = body["items"][0]
    assert first["period"] == "2026-05-26"
    assert Decimal(first["profit"]) == Decimal("570.00")
    assert first["trade_count"] == 2

    second = body["items"][1]
    assert second["period"] == "2026-05-25"
    assert Decimal(second["profit"]) == Decimal("-100.00")
    assert second["trade_count"] == 1


@pytest.mark.asyncio
async def test_pnl_history_weekly_groups_by_iso_week(client, db_session):
    db_session.add_all([
        Trade(
            id=uuid4(), ticket=2001, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 18), close_time=_bkk(2026, 5, 18, 15),
            open_price=Decimal("1950"), close_price=Decimal("1955"),
            volume=Decimal("0.10"), profit=Decimal("500.00"),
        ),
        Trade(
            id=uuid4(), ticket=2002, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 22), close_time=_bkk(2026, 5, 22, 15),
            open_price=Decimal("1955"), close_price=Decimal("1960"),
            volume=Decimal("0.10"), profit=Decimal("500.00"),
        ),
        Trade(
            id=uuid4(), ticket=2003, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 25), close_time=_bkk(2026, 5, 25, 15),
            open_price=Decimal("1960"), close_price=Decimal("1965"),
            volume=Decimal("0.10"), profit=Decimal("500.00"),
        ),
    ])
    await db_session.commit()

    res = await client.get("/api/pnl-history?granularity=weekly")
    body = res.json()
    assert body["total_count"] == 2
    assert body["items"][0]["period"] == "2026-05-25"  # Mon of ISO week 22
    assert Decimal(body["items"][0]["profit"]) == Decimal("500.00")
    assert body["items"][0]["trade_count"] == 1
    assert body["items"][1]["period"] == "2026-05-18"
    assert Decimal(body["items"][1]["profit"]) == Decimal("1000.00")
    assert body["items"][1]["trade_count"] == 2


@pytest.mark.asyncio
async def test_pnl_history_monthly_groups_by_first_of_month(client, db_session):
    db_session.add_all([
        Trade(
            id=uuid4(), ticket=3001, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 4, 15), close_time=_bkk(2026, 4, 15, 15),
            open_price=Decimal("1950"), close_price=Decimal("1955"),
            volume=Decimal("0.10"), profit=Decimal("200.00"),
        ),
        Trade(
            id=uuid4(), ticket=3002, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 5), close_time=_bkk(2026, 5, 5, 15),
            open_price=Decimal("1955"), close_price=Decimal("1960"),
            volume=Decimal("0.10"), profit=Decimal("700.00"),
        ),
    ])
    await db_session.commit()

    res = await client.get("/api/pnl-history?granularity=monthly")
    body = res.json()
    assert body["total_count"] == 2
    assert body["items"][0]["period"] == "2026-05-01"
    assert Decimal(body["items"][0]["profit"]) == Decimal("700.00")
    assert body["items"][1]["period"] == "2026-04-01"
    assert Decimal(body["items"][1]["profit"]) == Decimal("200.00")


@pytest.mark.asyncio
async def test_pnl_history_all_returns_row_per_trade(client, db_session):
    db_session.add_all([
        Trade(
            id=uuid4(), ticket=4001, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 26, 10), close_time=_bkk(2026, 5, 26, 11),
            open_price=Decimal("1955"), close_price=Decimal("1958"),
            volume=Decimal("0.05"), profit=Decimal("150.00"),
        ),
        Trade(
            id=uuid4(), ticket=4002, symbol="XAUUSD", direction=Direction.buy,
            order_state=OrderState.filled, is_paper=False,
            open_time=_bkk(2026, 5, 26, 14), close_time=_bkk(2026, 5, 26, 16),
            open_price=Decimal("1958"), close_price=Decimal("1960"),
            volume=Decimal("0.10"), profit=Decimal("200.00"),
        ),
    ])
    await db_session.commit()

    res = await client.get("/api/pnl-history?granularity=all")
    body = res.json()
    assert body["total_count"] == 2
    assert all(item["trade_count"] == 1 for item in body["items"])
    # newest first
    assert body["items"][0]["period"].startswith("2026-05-26")
    assert Decimal(body["items"][0]["profit"]) == Decimal("200.00")

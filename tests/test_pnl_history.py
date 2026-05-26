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

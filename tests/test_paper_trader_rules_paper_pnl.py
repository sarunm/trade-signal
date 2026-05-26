from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from models.pattern import PaperTraderRule, Pattern
from models.trade import Direction, OrderState, Trade

_BKK = timezone(timedelta(hours=7))


@pytest.mark.asyncio
async def test_paper_trader_rule_pnl_today_and_week(client, db_session):
    today = datetime(2026, 5, 26, 12, tzinfo=_BKK).astimezone(timezone.utc)
    yesterday = today - timedelta(days=1)
    week_old = today - timedelta(days=8)

    pattern = Pattern(
        id=uuid4(), indicator_slugs=["rsi_14"], timeframe="M15",
        win_rate=0.6, sample_count=20, consecutive_stable_days=3,
        status="active", discovered_at=today,
    )
    rule = PaperTraderRule(
        id=uuid4(), pattern_id=pattern.id, status="active",
        spawned_at=today, total_trades=0, win_count=0,
        virtual_balance_start=Decimal("5000"), virtual_balance_current=Decimal("5500"),
    )
    db_session.add_all([
        pattern, rule,
        Trade(id=uuid4(), ticket=20001, symbol="XAUUSD", direction=Direction.buy,
              order_state=OrderState.filled, is_paper=True,
              paper_trader_rule_id=rule.id,
              open_time=today, close_time=today,
              open_price=Decimal("1955"), close_price=Decimal("1960"),
              volume=Decimal("0.10"), profit=Decimal("100.00")),
        Trade(id=uuid4(), ticket=20002, symbol="XAUUSD", direction=Direction.buy,
              order_state=OrderState.filled, is_paper=True,
              paper_trader_rule_id=rule.id,
              open_time=yesterday, close_time=yesterday,
              open_price=Decimal("1955"), close_price=Decimal("1960"),
              volume=Decimal("0.10"), profit=Decimal("250.00")),
        Trade(id=uuid4(), ticket=20003, symbol="XAUUSD", direction=Direction.buy,
              order_state=OrderState.filled, is_paper=True,
              paper_trader_rule_id=rule.id,
              open_time=week_old, close_time=week_old,
              open_price=Decimal("1955"), close_price=Decimal("1960"),
              volume=Decimal("0.10"), profit=Decimal("999.00")),
    ])
    await db_session.commit()

    res = await client.get("/api/paper-trader-rules")
    rows = res.json()
    assert len(rows) == 1
    row = rows[0]
    assert Decimal(row["paper_pnl_today"]) >= Decimal("0")
    assert Decimal(row["paper_pnl_week"]) >= Decimal(row["paper_pnl_today"])
    assert Decimal(row["paper_pnl_week"]) < Decimal("999.00")

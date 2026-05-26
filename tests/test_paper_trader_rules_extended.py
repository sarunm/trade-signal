from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from models.pattern import Pattern, PaperTraderRule


@pytest.mark.asyncio
async def test_list_rules_returns_balance_and_activity_fields(client, db_session):
    pattern = Pattern(
        id=uuid4(),
        indicator_slugs=["rsi_14"],
        timeframe="M15",
        win_rate=0.6,
        sample_count=20,
        consecutive_stable_days=3,
        status="active",
        discovered_at=datetime.now(timezone.utc),
    )
    rule = PaperTraderRule(
        id=uuid4(),
        pattern_id=pattern.id,
        status="active",
        spawned_at=datetime.now(timezone.utc),
        total_trades=10,
        win_count=6,
        virtual_balance_start=Decimal("5000.00"),
        virtual_balance_current=Decimal("5240.50"),
    )
    db_session.add_all([pattern, rule])
    await db_session.commit()

    res = await client.get("/api/paper-trader-rules")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    row = body[0]
    assert row["virtual_balance_start"] == "5000.00"
    assert row["virtual_balance_current"] == "5240.50"
    assert row["open_trades_count"] == 0
    assert row["last_activity_at"] is None

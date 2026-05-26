import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base, get_session
from main import app
from models.paper_signal import PaperSignal
from models.pattern import PaperTraderRule, Pattern


@pytest_asyncio.fixture
async def client():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(eng, expire_on_commit=False)

    async def _override():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    async with Session() as setup:
        pattern = Pattern(
            indicator_slugs=["rsi", "ema"], timeframe="H1",
            win_rate=0.6, sample_count=20, status="active",
        )
        setup.add(pattern)
        await setup.flush()
        rule = PaperTraderRule(pattern_id=pattern.id, status="active", mode="strict")
        setup.add(rule)
        await setup.flush()
        for i, status in enumerate(["far", "near", "active"]):
            setup.add(PaperSignal(
                rule_id=rule.id, status=status, match_pct=Decimal("0.5"),
                matched_conditions=["rsi"], missing_conditions=["ema"],
                emitted_at=datetime(2026, 5, 25, 12, i, tzinfo=timezone.utc),
            ))
        await setup.commit()
        rule_id = rule.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, rule_id
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_list_paper_signals_for_rule(client):
    c, rule_id = client
    res = await c.get(f"/api/paper-signals?rule_id={rule_id}")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 3
    statuses = [d["status"] for d in data]
    assert statuses == ["active", "near", "far"]


@pytest.mark.asyncio
async def test_list_paper_signals_since_filter(client):
    c, rule_id = client
    cutoff = datetime(2026, 5, 25, 12, 1, tzinfo=timezone.utc).isoformat()
    res = await c.get("/api/paper-signals", params={"rule_id": str(rule_id), "since": cutoff})
    assert res.status_code == 200
    data = res.json()
    statuses = [d["status"] for d in data]
    assert "far" not in statuses

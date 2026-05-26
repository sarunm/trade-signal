from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base, get_session
from main import app
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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c._session_factory = Session
        yield c
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_shadows_endpoint_returns_parent_and_shadows(client):
    Session = client._session_factory
    async with Session() as s:
        pattern = Pattern(
            indicator_slugs=["rsi"], timeframe="H1",
            win_rate=0.6, sample_count=100, status="active",
        )
        s.add(pattern)
        await s.flush()
        parent = PaperTraderRule(
            pattern_id=pattern.id, status="active", mode="strict",
            virtual_balance_start=Decimal("5000"),
            virtual_balance_current=Decimal("5000"),
        )
        s.add(parent)
        await s.flush()
        shadow = PaperTraderRule(
            pattern_id=pattern.id, status="shadow", mode="strict",
            virtual_balance_start=Decimal("5000"),
            virtual_balance_current=Decimal("5000"),
            filters=[{"feature": "session", "exclude": "asia"}],
            shadow_of_rule_id=parent.id,
        )
        s.add(shadow)
        await s.commit()
        parent_id = str(parent.id)
        shadow_id = str(shadow.id)

    res = await client.get(f"/api/paper-trader-rules/{parent_id}/shadows")
    assert res.status_code == 200
    body = res.json()
    assert body["parent"]["id"] == parent_id
    ids = [s["id"] for s in body["shadows"]]
    assert shadow_id in ids
    s0 = body["shadows"][0]
    assert s0["filters"] == [{"feature": "session", "exclude": "asia"}]
    assert "winrate_delta" in s0


@pytest.mark.asyncio
async def test_shadows_endpoint_404_for_unknown_id(client):
    res = await client.get(f"/api/paper-trader-rules/{uuid4()}/shadows")
    assert res.status_code == 404

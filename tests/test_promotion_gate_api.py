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
    async with Session() as setup:
        pattern = Pattern(
            indicator_slugs=["a", "b"], timeframe="H1",
            win_rate=0.6, sample_count=20, status="active",
        )
        setup.add(pattern)
        await setup.flush()
        rule = PaperTraderRule(
            pattern_id=pattern.id, status="active",
            mode="basket_5k", total_trades=50, win_count=30,
        )
        setup.add(rule)
        await setup.commit()
        rule_id = rule.id
        pattern_id = pattern.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, pattern_id, rule_id

    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_pattern_gates_endpoint_returns_breakdown(client):
    c, pattern_id, _ = client
    res = await c.get(f"/api/patterns/{pattern_id}/gates")
    assert res.status_code == 200
    data = res.json()
    assert "rules" in data
    assert len(data["rules"]) == 1
    rule_summary = data["rules"][0]
    for key in (
        "rule_id", "tier", "gates", "wilson_lower", "net_ev",
        "profit_factor", "baseline_delta",
    ):
        assert key in rule_summary
    assert set(rule_summary["gates"].keys()) == {
        "sample", "performance", "stability", "walk_forward",
    }

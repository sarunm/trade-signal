import pytest
import pytest_asyncio
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_paper_trader_rules_has_v2_promotion_columns(engine):
    async with engine.connect() as conn:
        cols = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("paper_trader_rules")}
        )
    expected = {
        "trust_tier", "is_baseline", "spawn_strategy",
        "net_ev_per_trade", "wilson_lower_95", "baseline_delta",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"

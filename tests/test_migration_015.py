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
async def test_cost_calibrations_exists(engine):
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert "cost_calibrations" in tables


@pytest.mark.asyncio
async def test_cost_calibrations_columns(engine):
    async with engine.connect() as conn:
        cols = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("cost_calibrations")}
        )
    expected = {
        "id", "learned_spread_pip", "learned_commission_per_lot_thb",
        "sample_count_spread", "sample_count_commission", "calibrated_at",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"

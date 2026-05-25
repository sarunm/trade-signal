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
async def test_paper_trader_rules_has_redesign_columns(engine):
    async with engine.connect() as conn:
        cols = await conn.run_sync(
            lambda sync_conn: {c["name"] for c in inspect(sync_conn).get_columns("paper_trader_rules")}
        )
    expected = {
        "mode", "virtual_balance_start", "virtual_balance_current",
        "score_weights", "filters", "shadow_of_rule_id",
        "gate_status", "promoted_at", "consecutive_stable_days",
        "last_signal_status",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


@pytest.mark.asyncio
async def test_paper_signals_table_exists(engine):
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert "paper_signals" in tables


@pytest.mark.asyncio
async def test_score_calibrations_table_exists(engine):
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert "score_calibrations" in tables

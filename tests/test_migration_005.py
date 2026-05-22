import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base


@pytest.mark.asyncio
async def test_trade_model_has_entry_context_columns():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with engine.connect() as conn:
        cols = await conn.run_sync(
            lambda sync_conn: [
                c["name"] for c in inspect(sync_conn).get_columns("trades")
            ]
        )
    expected = [
        "setup_pattern",
        "trade_bias",
        "near_fib_level",
        "fib_distance_pts",
        "entry_candle",
        "entry_candle_tf",
        "is_rescue",
        "post_close_run_pts",
    ]
    for col in expected:
        assert col in cols, f"Missing column: {col}"
    await engine.dispose()

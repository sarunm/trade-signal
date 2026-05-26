from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models.trade import Direction, OrderState, OrderType, PaperMode, Trade
from services.baseline_runner import ensure_baseline_rule
from services.baseline_stats import get_baseline_winrate


@pytest_asyncio.fixture
async def session():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(eng, expire_on_commit=False)
    async with Session() as s:
        yield s
    await eng.dispose()


def _baseline_trade(rule_id, close_time: datetime, profit: float, ticket: int) -> Trade:
    return Trade(
        ticket=ticket,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_type=OrderType.market,
        order_state=OrderState.filled,
        open_time=close_time - timedelta(hours=1),
        close_time=close_time,
        open_price=Decimal("1950"),
        close_price=Decimal("1955") if profit > 0 else Decimal("1945"),
        volume=Decimal("0.10"),
        profit=Decimal(str(profit)),
        is_paper=True,
        paper_mode=PaperMode.independent,
        recovery_plan={"paper_trader_rule_id": str(rule_id), "is_baseline": True},
    )


@pytest.mark.asyncio
async def test_baseline_winrate_returns_zero_with_no_trades(session):
    await ensure_baseline_rule(session)
    assert await get_baseline_winrate(session, days=30) == 0.0


@pytest.mark.asyncio
async def test_baseline_winrate_three_of_five_wins(session):
    rule = await ensure_baseline_rule(session)
    base = datetime.now(timezone.utc) - timedelta(days=5)
    for i, profit in enumerate([10, -5, 15, -8, 20]):
        session.add(_baseline_trade(rule.id, base + timedelta(hours=i), profit, ticket=i + 100))
    await session.commit()
    assert await get_baseline_winrate(session, days=30) == 0.6


@pytest.mark.asyncio
async def test_baseline_winrate_excludes_outside_window(session):
    rule = await ensure_baseline_rule(session)
    old = datetime.now(timezone.utc) - timedelta(days=60)
    new = datetime.now(timezone.utc) - timedelta(days=2)
    session.add(_baseline_trade(rule.id, old, profit=10, ticket=1))
    session.add(_baseline_trade(rule.id, new, profit=-5, ticket=2))
    await session.commit()
    assert await get_baseline_winrate(session, days=30) == 0.0

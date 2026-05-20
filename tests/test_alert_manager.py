import pytest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from models.trade import Trade, Direction, OrderState
from models.alert import Alert
from services.alert_manager import check_trade_alerts, check_equity_buffer, check_insight_alerts
from schemas.trade_event import TradeEventSchema
from schemas.price_tick import PriceTickSchema, AccountStateSchema, OHLCVSchema


def _filled_buy(ticket: int, profit: float = None, close: bool = False) -> Trade:
    t = Trade(
        id=uuid.uuid4(),
        ticket=ticket,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("1950.00"),
        volume=Decimal("1.00"),
        open_time=datetime.now(timezone.utc),
        is_paper=False,
    )
    if close and profit is not None:
        t.close_price = Decimal("1940.00") if profit < 0 else Decimal("1960.00")
        t.close_time = datetime.now(timezone.utc)
        t.profit = Decimal(str(profit))
    return t


def _event(ticket: int, order_state: str = "filled", direction: str = "buy",
           profit: float = None, close_price: float = None) -> TradeEventSchema:
    return TradeEventSchema(
        transaction_type="DEAL_ADD",
        ticket=ticket,
        symbol="XAUUSD",
        direction=direction,
        order_type="market",
        order_state=order_state,
        open_price=Decimal("1950.00") if close_price is None else None,
        close_price=Decimal(str(close_price)) if close_price else None,
        close_time=datetime.now(timezone.utc) if close_price else None,
        profit=Decimal(str(profit)) if profit is not None else None,
        volume=Decimal("1.00"),
        open_time=datetime.now(timezone.utc) if close_price is None else None,
    )


def _tick(free_margin: float, total_volume: float = 0.0) -> PriceTickSchema:
    return PriceTickSchema(
        timestamp=datetime.now(timezone.utc),
        symbol="XAUUSD",
        account=AccountStateSchema(
            equity=Decimal("10500.00"),
            balance=Decimal("10000.00"),
            margin=Decimal("450.00"),
            free_margin=Decimal(str(free_margin)),
            floating_pl=Decimal("-500.00"),
        ),
        bars={
            "H1": OHLCVSchema(open=Decimal("1950"), high=Decimal("1955"),
                              low=Decimal("1945"), close=Decimal("1952"), volume=Decimal("1000")),
        },
    )


@pytest.mark.asyncio
async def test_double_down_alert_fires(db_session):
    """Alert when user adds to same-direction open position."""
    existing = _filled_buy(ticket=1000)
    db_session.add(existing)
    await db_session.commit()

    event = _event(ticket=1001, direction="buy")
    await check_trade_alerts(db_session, event)

    result = await db_session.execute(select(Alert).where(Alert.type == "double_down"))
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert "buy" in alerts[0].message


@pytest.mark.asyncio
async def test_no_double_down_alert_on_first_trade(db_session):
    """No alert when there are no existing open positions."""
    event = _event(ticket=1001, direction="buy")
    await check_trade_alerts(db_session, event)

    result = await db_session.execute(select(Alert).where(Alert.type == "double_down"))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_consecutive_loss_alert_fires(db_session):
    """Alert after 3 consecutive losses."""
    for i, ticket in enumerate([1001, 1002, 1003]):
        t = _filled_buy(ticket=ticket, profit=-100.0, close=True)
        db_session.add(t)
    await db_session.commit()

    # Close event for trade 1003 (already in DB)
    event = _event(ticket=1003, close_price=1940.0, profit=-100.0)
    await check_trade_alerts(db_session, event)

    result = await db_session.execute(select(Alert).where(Alert.type == "consecutive_loss"))
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert "3" in alerts[0].message


@pytest.mark.asyncio
async def test_no_consecutive_loss_alert_after_win(db_session):
    """No alert when streak is broken by a win."""
    for i, profit in enumerate([-100.0, 50.0, -100.0]):
        t = _filled_buy(ticket=1000 + i, profit=profit, close=True)
        db_session.add(t)
    await db_session.commit()

    event = _event(ticket=9999, close_price=1940.0, profit=-100.0)
    await check_trade_alerts(db_session, event)

    result = await db_session.execute(select(Alert).where(Alert.type == "consecutive_loss"))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_equity_buffer_alert_fires(db_session):
    """Alert when free_margin below required buffer for open lots."""
    # 1 lot open: required = 1.0 * 10000 = 10000 USD
    open_trade = _filled_buy(ticket=1001)
    db_session.add(open_trade)
    await db_session.commit()

    tick = _tick(free_margin=5000.0)  # below 10000 required
    await check_equity_buffer(db_session, tick)

    result = await db_session.execute(select(Alert).where(Alert.type == "equity_buffer"))
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert "5000" in alerts[0].message


@pytest.mark.asyncio
async def test_equity_buffer_no_alert_when_sufficient(db_session):
    """No alert when free_margin exceeds required buffer."""
    open_trade = _filled_buy(ticket=1001)
    db_session.add(open_trade)
    await db_session.commit()

    tick = _tick(free_margin=15000.0)  # above 10000 required
    await check_equity_buffer(db_session, tick)

    result = await db_session.execute(select(Alert).where(Alert.type == "equity_buffer"))
    assert result.scalars().all() == []


# ── large_adverse_move ────────────────────────────────────────────────────────

from schemas.market_tick import MarketTickSchema
from services.alert_manager import check_large_adverse_move


def _market_tick(bid: float, ask: float, symbol: str = "XAUUSD") -> MarketTickSchema:
    return MarketTickSchema(
        timestamp=datetime.now(timezone.utc),
        symbol=symbol,
        bid=Decimal(str(bid)),
        ask=Decimal(str(ask)),
    )


@pytest.mark.asyncio
async def test_large_adverse_move_alert_fires_for_buy(db_session):
    """Alert fires when buy trade has bid 200+ pts below entry."""
    trade = _filled_buy(ticket=2001)
    trade.open_price = Decimal("2000.00")
    db_session.add(trade)
    await db_session.commit()

    tick = _market_tick(bid=1799.00, ask=1799.20)  # 201 pts adverse
    await check_large_adverse_move(db_session, tick)

    result = await db_session.execute(select(Alert).where(Alert.type == "large_adverse_move"))
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert "2001" in alerts[0].message
    assert alerts[0].trigger_data["direction"] == "buy"


@pytest.mark.asyncio
async def test_large_adverse_move_alert_fires_for_sell(db_session):
    """Alert fires when sell trade has ask 200+ pts above entry."""
    trade = Trade(
        id=uuid.uuid4(),
        ticket=2002,
        symbol="XAUUSD",
        direction=Direction.sell,
        order_state=OrderState.filled,
        open_price=Decimal("2000.00"),
        volume=Decimal("1.00"),
        open_time=datetime.now(timezone.utc),
        is_paper=False,
    )
    db_session.add(trade)
    await db_session.commit()

    tick = _market_tick(bid=2200.80, ask=2201.00)  # 201 pts adverse for sell
    await check_large_adverse_move(db_session, tick)

    result = await db_session.execute(select(Alert).where(Alert.type == "large_adverse_move"))
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert alerts[0].trigger_data["direction"] == "sell"


@pytest.mark.asyncio
async def test_large_adverse_move_no_alert_when_small_move(db_session):
    """No alert when adverse move is under threshold."""
    trade = _filled_buy(ticket=2003)
    trade.open_price = Decimal("2000.00")
    db_session.add(trade)
    await db_session.commit()

    tick = _market_tick(bid=1850.00, ask=1850.20)  # only 150 pts adverse
    await check_large_adverse_move(db_session, tick)

    result = await db_session.execute(select(Alert).where(Alert.type == "large_adverse_move"))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_large_adverse_move_no_duplicate_within_cooldown(db_session):
    """Only one alert fires per ticket within the cooldown window."""
    trade = _filled_buy(ticket=2004)
    trade.open_price = Decimal("2000.00")
    db_session.add(trade)
    await db_session.commit()

    tick = _market_tick(bid=1799.00, ask=1799.20)
    await check_large_adverse_move(db_session, tick)
    await check_large_adverse_move(db_session, tick)  # second call same tick

    result = await db_session.execute(select(Alert).where(Alert.type == "large_adverse_move"))
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_low_winrate_setup_alert_fires(db_session):
    """Alert fires when setup+bias combo has < 40% win rate with 5+ trades."""
    trades = []
    for i in range(5):
        trade = Trade(
            id=uuid.uuid4(),
            ticket=8000 + i,
            symbol="XAUUSD",
            direction=Direction.buy,
            order_state=OrderState.filled,
            open_price=Decimal("2000.00"),
            open_time=datetime(2026, 5, 19, 10, i, tzinfo=timezone.utc),
            close_time=datetime(2026, 5, 19, 11, i, tzinfo=timezone.utc),
            profit=Decimal("-100.00"),
            is_paper=False,
            setup_pattern="double_top",
            trade_bias="bullish",
        )
        db_session.add(trade)
        trades.append(trade)
    await db_session.commit()

    await check_insight_alerts(db_session, trades, trades)

    result = await db_session.execute(
        select(Alert).where(Alert.type == "low_winrate_setup")
    )
    alerts = result.scalars().all()
    assert len(alerts) == 1
    assert "double_top" in alerts[0].message


@pytest.mark.asyncio
async def test_low_winrate_setup_no_alert_when_good_winrate(db_session):
    """No alert when win rate is >= 40%."""
    for i in range(5):
        profit = Decimal("200.00") if i < 4 else Decimal("-100.00")
        trade = Trade(
            id=uuid.uuid4(),
            ticket=8100 + i,
            symbol="XAUUSD",
            direction=Direction.buy,
            order_state=OrderState.filled,
            open_price=Decimal("2000.00"),
            open_time=datetime(2026, 5, 19, 10, i, tzinfo=timezone.utc),
            close_time=datetime(2026, 5, 19, 11, i, tzinfo=timezone.utc),
            profit=profit,
            is_paper=False,
            setup_pattern="double_bottom",
            trade_bias="bullish",
        )
        db_session.add(trade)
    await db_session.commit()

    tagged = (await db_session.execute(
        select(Trade).where(Trade.setup_pattern.isnot(None))
    )).scalars().all()

    await check_insight_alerts(db_session, tagged, tagged)

    result = await db_session.execute(
        select(Alert).where(Alert.type == "low_winrate_setup")
    )
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_rescue_ineffective_alert_fires(db_session):
    """Alert fires when rescue win_rate < 35% and delta > 20pp vs initial."""
    # 5 initial trades: 80% win rate
    for i in range(4):
        trade = Trade(
            id=uuid.uuid4(),
            ticket=9000 + i,
            symbol="XAUUSD",
            direction=Direction.buy,
            order_state=OrderState.filled,
            open_price=Decimal("2000.00"),
            open_time=datetime(2026, 5, 19, 10, i, tzinfo=timezone.utc),
            close_time=datetime(2026, 5, 19, 11, i, tzinfo=timezone.utc),
            profit=Decimal("200.00"),
            is_paper=False,
            is_rescue=False,
        )
        db_session.add(trade)
    trade = Trade(
        id=uuid.uuid4(),
        ticket=9004,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        open_price=Decimal("2000.00"),
        open_time=datetime(2026, 5, 19, 10, 4, tzinfo=timezone.utc),
        close_time=datetime(2026, 5, 19, 11, 4, tzinfo=timezone.utc),
        profit=Decimal("-100.00"),
        is_paper=False,
        is_rescue=False,
    )
    db_session.add(trade)

    # 5 rescue trades: 0% win rate
    for i in range(5):
        trade = Trade(
            id=uuid.uuid4(),
            ticket=9100 + i,
            symbol="XAUUSD",
            direction=Direction.buy,
            order_state=OrderState.filled,
            open_price=Decimal("2000.00"),
            open_time=datetime(2026, 5, 19, 12, i, tzinfo=timezone.utc),
            close_time=datetime(2026, 5, 19, 13, i, tzinfo=timezone.utc),
            profit=Decimal("-100.00"),
            is_paper=False,
            is_rescue=True,
        )
        db_session.add(trade)

    await db_session.commit()

    all_trades = (await db_session.execute(
        select(Trade).where(Trade.is_paper == False)
    )).scalars().all()
    await check_insight_alerts(db_session, all_trades, all_trades)

    result = await db_session.execute(
        select(Alert).where(Alert.type == "rescue_ineffective")
    )
    alerts = result.scalars().all()
    assert len(alerts) == 1

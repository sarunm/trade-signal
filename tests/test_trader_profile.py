from datetime import datetime, timezone
from decimal import Decimal

import pytest
from models.account_snapshot import AccountSnapshot
from models.trade import Direction, OrderState, Trade
from schemas.trader_profile import CandidateRule, TraderProfileResponse, TraderProfileSummary


def test_candidate_rule_win_rate_optional():
    candidate = CandidateRule(
        setup_pattern="support",
        trade_bias="bullish",
        count=2,
        win_rate=None,
        threshold=15,
    )

    assert candidate.win_rate is None
    assert candidate.threshold == 15


def test_trader_profile_response_structure():
    summary = TraderProfileSummary(
        dominant_setup="support",
        dominant_bias="bullish",
        dominant_entry=None,
        dominant_fib=None,
        rescue_rate=0.25,
        total_tagged=8,
    )
    profile = TraderProfileResponse(summary=summary, candidates=[])

    assert profile.summary.total_tagged == 8
    assert profile.candidates == []


def _tagged_trade(ticket: int, profit: str, setup_pattern="support", trade_bias="bullish"):
    return Trade(
        ticket=ticket,
        symbol="XAUUSD",
        direction=Direction.buy,
        order_state=OrderState.filled,
        is_paper=False,
        open_price=Decimal("3280.00"),
        close_price=Decimal("3290.00"),
        profit=Decimal(profit),
        setup_pattern=setup_pattern,
        trade_bias=trade_bias,
        open_time=datetime.now(timezone.utc),
        close_time=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_trader_profile_empty(client):
    response = await client.get("/api/trader-profile")

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_tagged"] == 0
    assert data["summary"]["rescue_rate"] == 0.0
    assert data["candidates"] == []


@pytest.mark.asyncio
async def test_trader_profile_win_rate_hidden_below_3(client, db_session):
    db_session.add_all([
        _tagged_trade(9001, "10.00"),
        _tagged_trade(9002, "-7.00"),
    ])
    await db_session.commit()

    response = await client.get("/api/trader-profile")

    assert response.status_code == 200
    data = response.json()
    candidate = next(c for c in data["candidates"] if c["setup_pattern"] == "support")
    assert candidate["count"] == 2
    assert candidate["win_rate"] is None


@pytest.mark.asyncio
async def test_trader_profile_win_rate_shown_at_3(client, db_session):
    db_session.add_all([
        _tagged_trade(9003, "10.00"),
        _tagged_trade(9004, "10.00"),
        _tagged_trade(9005, "-7.00"),
    ])
    await db_session.commit()

    response = await client.get("/api/trader-profile")

    assert response.status_code == 200
    data = response.json()
    candidate = next(c for c in data["candidates"] if c["setup_pattern"] == "support")
    assert candidate["count"] == 3
    assert candidate["win_rate"] == pytest.approx(2 / 3, abs=0.01)


@pytest.mark.asyncio
async def test_trader_profile_filters_to_current_account(client, db_session):
    db_session.add(
        AccountSnapshot(
            timestamp=datetime.now(timezone.utc),
            equity=Decimal("10000.00"),
            balance=Decimal("10000.00"),
            margin=Decimal("0.00"),
            free_margin=Decimal("10000.00"),
            floating_pl=Decimal("0.00"),
            account_id=335297575,
        )
    )
    matching = _tagged_trade(9006, "10.00", setup_pattern="support")
    matching.account_id = 335297575
    other = _tagged_trade(9007, "-7.00", setup_pattern="resistance")
    other.account_id = 999999
    db_session.add_all([matching, other])
    await db_session.commit()

    response = await client.get("/api/trader-profile")

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_tagged"] == 1
    assert data["summary"]["dominant_setup"] == "support"
    assert [candidate["setup_pattern"] for candidate in data["candidates"]] == ["support"]

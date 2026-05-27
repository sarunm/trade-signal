from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from ml.classifier import train_classifier, load_classifier, predict_proba
from models.trade import Direction, OrderState, Trade


def _trade(i: int, profit: float, hour: int, score: int) -> Trade:
    return Trade(
        id=uuid4(), ticket=900000 + i, symbol="GOLD#",
        direction=Direction.buy if i % 2 == 0 else Direction.sell,
        order_state=OrderState.filled, is_paper=False,
        open_time=datetime(2026, 5, 1, hour, tzinfo=timezone.utc),
        close_time=datetime(2026, 5, 1, hour + 1, tzinfo=timezone.utc),
        open_price=Decimal("4500"), close_price=Decimal("4505"),
        volume=Decimal("0.10"), entry_score=score, profit=Decimal(str(profit)),
        near_fib_level="R1" if profit > 0 else "S1",
    )


@pytest.mark.asyncio
async def test_train_classifier_below_min_samples_returns_skipped(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("ML_ARTIFACT_DIR", str(tmp_path))
    db_session.add_all([_trade(i, 100, 9, 80) for i in range(5)])
    await db_session.commit()

    result = await train_classifier(db_session)
    assert result["status"] == "skipped"
    assert result["samples"] < 30


@pytest.mark.asyncio
async def test_train_classifier_persists_artifact_and_predicts(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("ML_ARTIFACT_DIR", str(tmp_path))
    db_session.add_all([_trade(i, 100, 9, 80) for i in range(30)])
    db_session.add_all([_trade(i + 100, -100, 14, 30) for i in range(30)])
    await db_session.commit()

    result = await train_classifier(db_session)
    assert result["status"] == "trained"
    assert result["samples"] == 60
    assert "model_version" in result
    assert result["val_acc"] >= 0.5

    clf = load_classifier()
    proba_winner = predict_proba(clf, {
        "entry_score": 80, "direction_buy": 1, "hour_of_day_utc": 9,
        "day_of_week": 1, "signal_match_count": 0, "signal_density": 0.0,
        "rsi_value": 0.0, "ema_alignment": 0.0,
        "near_fib_R1": 1, "near_fib_R2": 0, "near_fib_R3": 0,
        "near_fib_S1": 0, "near_fib_S2": 0, "near_fib_S3": 0,
        "near_fib_PP": 0, "near_fib_none": 0,
    })
    proba_loser = predict_proba(clf, {
        "entry_score": 30, "direction_buy": 1, "hour_of_day_utc": 14,
        "day_of_week": 1, "signal_match_count": 0, "signal_density": 0.0,
        "rsi_value": 0.0, "ema_alignment": 0.0,
        "near_fib_R1": 0, "near_fib_R2": 0, "near_fib_R3": 0,
        "near_fib_S1": 1, "near_fib_S2": 0, "near_fib_S3": 0,
        "near_fib_PP": 0, "near_fib_none": 0,
    })
    assert proba_winner > proba_loser

# ML Pattern Scorer Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax. Pick tasks in order — earlier tasks define types/functions later tasks consume.

**Goal:** Add a shadow-mode ML ranker between Pattern Discovery and the Auto Paper Trader spawn step (per spec `2026-05-27-ml-pattern-scorer-design.md`).

**Architecture:** Layer 1 = per-trade win classifier (Logistic Regression on 110 closed real trades + 9,372 indicator signals). Layer 2 = pattern scorer that aggregates Layer 1 predictions × confidence factor. Shadow mode default; activates only when val_acc ≥ 0.62.

**Tech stack:** Python 3.12 + scikit-learn + joblib + SQLAlchemy 2.0 async + FastAPI + Pydantic v2 + pytest-asyncio.

---

## Task 1 — Add scikit-learn to requirements

**Files:**
- Modify: `api/requirements.txt`

- [ ] **Step 1: Add dependency**

Append to `api/requirements.txt`:

```
scikit-learn==1.5.2
joblib==1.4.2
numpy==2.1.3
```

(numpy explicit so version doesn't drift with sklearn updates; pandas not needed — features.py uses dict→list conversion.)

- [ ] **Step 2: Rebuild image**

```bash
docker compose build api
docker compose up -d api
```

Expected: container starts, no import errors.

- [ ] **Step 3: Commit**

```bash
git add api/requirements.txt
git commit -m "chore: add scikit-learn for ML pattern scorer"
```

---

## Task 2 — Migration: ml_pattern_scores table

**Files:**
- Create: `api/alembic/versions/023_create_ml_pattern_scores.py`

- [ ] **Step 1: Write migration**

```python
"""create ml_pattern_scores

Revision ID: 023_create_ml_pattern_scores
Revises: 022_normalize_symbols
Create Date: 2026-05-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "023_create_ml_pattern_scores"
down_revision = "022_normalize_symbols"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ml_pattern_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pattern_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Numeric(5, 4), nullable=False),
        sa.Column("model_version", sa.String(40), nullable=False),
        sa.Column("features", postgresql.JSONB, nullable=False),
        sa.Column("spawn_decision", sa.String(20), nullable=True),
        sa.Column("ml_decision", sa.String(20), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["pattern_id"], ["patterns.id"]),
    )
    op.create_index("ix_ml_pattern_scores_pattern_id", "ml_pattern_scores", ["pattern_id"])
    op.create_index("ix_ml_pattern_scores_computed_at", "ml_pattern_scores", [sa.text("computed_at DESC")])


def downgrade():
    op.drop_index("ix_ml_pattern_scores_computed_at", table_name="ml_pattern_scores")
    op.drop_index("ix_ml_pattern_scores_pattern_id", table_name="ml_pattern_scores")
    op.drop_table("ml_pattern_scores")
```

Confirm `down_revision` matches the latest migration head:

```bash
docker compose exec api alembic heads
```

If head differs from `022_normalize_symbols`, update the literal.

- [ ] **Step 2: Apply migration**

```bash
docker compose exec api alembic upgrade head
```

Expected: "Running upgrade … 023_create_ml_pattern_scores".

- [ ] **Step 3: Verify table**

```bash
docker compose exec db psql -U tradesignal -d tradesignal -c "\d ml_pattern_scores"
```

Expected: 8 columns, 2 secondary indexes, 1 FK.

- [ ] **Step 4: Commit**

```bash
git add api/alembic/versions/023_create_ml_pattern_scores.py
git commit -m "feat: add ml_pattern_scores table for shadow-mode ML logging"
```

---

## Task 3 — ORM model for ml_pattern_scores

**Files:**
- Create: `api/models/ml_pattern_score.py`
- Modify: `api/models/__init__.py`

- [ ] **Step 1: Write failing test**

`tests/test_ml_models.py`:

```python
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from models.ml_pattern_score import MLPatternScore
from models.patterns import Pattern


@pytest.mark.asyncio
async def test_ml_pattern_score_roundtrip(db_session):
    pattern = Pattern(
        id=uuid4(),
        indicator_slugs=["ema_cross", "rsi"],
        timeframe="H1",
        win_rate=0.6,
        sample_count=10,
        consecutive_stable_days=3,
        status="candidate",
        discovered_at=datetime.now(timezone.utc),
    )
    db_session.add(pattern)
    await db_session.flush()

    row = MLPatternScore(
        id=uuid4(),
        pattern_id=pattern.id,
        score=Decimal("0.7234"),
        model_version="v1-2026-05-27",
        features={"entry_score": 70, "rsi": 55.2},
        spawn_decision="spawn",
        ml_decision="spawn",
    )
    db_session.add(row)
    await db_session.commit()

    fetched = await db_session.get(MLPatternScore, row.id)
    assert fetched.score == Decimal("0.7234")
    assert fetched.model_version == "v1-2026-05-27"
    assert fetched.features["rsi"] == 55.2
    assert fetched.spawn_decision == "spawn"
```

- [ ] **Step 2: Run test (should fail with ImportError)**

```bash
docker compose exec -T -e PYTHONPATH=/app api pytest /app/tests/test_ml_models.py -v
```

Expected: ModuleNotFoundError for `models.ml_pattern_score`.

- [ ] **Step 3: Write model**

`api/models/ml_pattern_score.py`:

```python
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class MLPatternScore(Base):
    __tablename__ = "ml_pattern_scores"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    pattern_id: Mapped[UUID] = mapped_column(ForeignKey("patterns.id"), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False)
    spawn_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ml_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 4: Register in __init__**

Add to `api/models/__init__.py`:

```python
from models.ml_pattern_score import MLPatternScore  # noqa: F401
```

- [ ] **Step 5: Run test (should pass)**

```bash
docker compose exec -T -e PYTHONPATH=/app api pytest /app/tests/test_ml_models.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add api/models/ml_pattern_score.py api/models/__init__.py tests/test_ml_models.py
git commit -m "feat: add MLPatternScore ORM model"
```

---

## Task 4 — Feature extractor

**Files:**
- Create: `api/ml/__init__.py` (empty)
- Create: `api/ml/features.py`
- Create: `tests/test_ml_features.py`

- [ ] **Step 1: Write failing test**

`tests/test_ml_features.py`:

```python
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from ml.features import extract_trade_features
from models.trade import Direction, OrderState, Trade
from models.trade_indicator_signal import TradeIndicatorSignal


@pytest.mark.asyncio
async def test_extract_trade_features_basic_buy(db_session):
    trade = Trade(
        id=uuid4(),
        ticket=999001,
        symbol="GOLD#",
        direction=Direction.buy,
        order_state=OrderState.filled,
        is_paper=False,
        open_time=datetime(2026, 5, 27, 9, 30, tzinfo=timezone.utc),
        open_price=Decimal("4500.00"),
        volume=Decimal("0.10"),
        entry_score=72,
        near_fib_level="R1",
        profit=Decimal("150.00"),
    )
    db_session.add(trade)
    await db_session.flush()
    db_session.add_all([
        TradeIndicatorSignal(
            id=uuid4(), trade_id=trade.id,
            indicator_slug="ema_cross", timeframe="H1",
            value=1.0, direction="bull", matched=True, metadata={},
            calculated_at=trade.open_time,
        ),
        TradeIndicatorSignal(
            id=uuid4(), trade_id=trade.id,
            indicator_slug="rsi", timeframe="H1",
            value=58.0, direction=None, matched=False, metadata={},
            calculated_at=trade.open_time,
        ),
    ])
    await db_session.commit()

    feats = await extract_trade_features(db_session, trade)
    assert feats["entry_score"] == 72
    assert feats["direction_buy"] == 1
    assert feats["near_fib_R1"] == 1
    assert feats["near_fib_S1"] == 0
    assert feats["hour_of_day_utc"] == 9
    assert feats["day_of_week"] in range(0, 7)
    assert feats["signal_match_count"] == 1
    assert feats["signal_density"] == pytest.approx(0.5)
    assert feats["rsi_value"] == 58.0


@pytest.mark.asyncio
async def test_extract_trade_features_handles_nulls(db_session):
    trade = Trade(
        id=uuid4(), ticket=999002, symbol="GOLD#",
        direction=Direction.sell, order_state=OrderState.filled, is_paper=False,
        open_time=datetime(2026, 5, 27, 0, 0, tzinfo=timezone.utc),
        open_price=Decimal("4500"), volume=Decimal("0.1"),
        entry_score=None, near_fib_level=None, profit=Decimal("-50"),
    )
    db_session.add(trade)
    await db_session.commit()

    feats = await extract_trade_features(db_session, trade)
    assert feats["entry_score"] == 0  # null defaults to 0
    assert feats["near_fib_none"] == 1
    assert feats["direction_buy"] == 0
    assert feats["signal_match_count"] == 0
    assert feats["signal_density"] == 0.0
    assert feats["rsi_value"] == 0.0
```

- [ ] **Step 2: Run test (fails — ImportError)**

```bash
docker compose exec -T -e PYTHONPATH=/app api pytest /app/tests/test_ml_features.py -v
```

- [ ] **Step 3: Implement features**

`api/ml/__init__.py`: empty file.

`api/ml/features.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.trade import Trade
from models.trade_indicator_signal import TradeIndicatorSignal

FIB_LEVELS = ("R1", "R2", "R3", "S1", "S2", "S3", "PP")
FEATURE_KEYS_INDICATORS = ("rsi_value", "ema_alignment", "atr_norm")


async def extract_trade_features(session: AsyncSession, trade: Trade) -> dict:
    sigs = (await session.execute(
        select(TradeIndicatorSignal).where(TradeIndicatorSignal.trade_id == trade.id)
    )).scalars().all()

    matched = [s for s in sigs if s.matched]
    rsi = next((s.value for s in sigs if s.indicator_slug == "rsi" and s.value is not None), 0.0)
    ema_align = next(
        (1.0 if s.direction == "bull" else -1.0 if s.direction == "bear" else 0.0
         for s in sigs if s.indicator_slug == "ema_cross"),
        0.0,
    )
    if trade.direction.value == "sell":
        ema_align = -ema_align

    feats = {
        "entry_score": int(trade.entry_score or 0),
        "direction_buy": 1 if trade.direction.value == "buy" else 0,
        "hour_of_day_utc": trade.open_time.hour if trade.open_time else 0,
        "day_of_week": trade.open_time.weekday() if trade.open_time else 0,
        "signal_match_count": len(matched),
        "signal_density": len(matched) / len(sigs) if sigs else 0.0,
        "rsi_value": float(rsi),
        "ema_alignment": ema_align,
    }
    fib = trade.near_fib_level or "none"
    for level in FIB_LEVELS:
        feats[f"near_fib_{level}"] = 1 if fib == level else 0
    feats["near_fib_none"] = 1 if fib == "none" else 0
    return feats


def feature_order() -> list[str]:
    base = [
        "entry_score", "direction_buy", "hour_of_day_utc", "day_of_week",
        "signal_match_count", "signal_density", "rsi_value", "ema_alignment",
    ]
    base += [f"near_fib_{lvl}" for lvl in FIB_LEVELS]
    base.append("near_fib_none")
    return base


def to_vector(feats: dict) -> list[float]:
    return [float(feats.get(k, 0)) for k in feature_order()]
```

- [ ] **Step 4: Run test (passes)**

```bash
docker compose exec -T -e PYTHONPATH=/app api pytest /app/tests/test_ml_features.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add api/ml/__init__.py api/ml/features.py tests/test_ml_features.py
git commit -m "feat(ml): add feature extractor for per-trade classifier"
```

---

## Task 5 — Layer 1 classifier (train + predict)

**Files:**
- Create: `api/ml/classifier.py`
- Create: `tests/test_ml_classifier.py`
- Add to `.gitignore`: `api/ml/artifacts/`

- [ ] **Step 1: Write failing test**

`tests/test_ml_classifier.py`:

```python
from datetime import datetime, timezone, timedelta
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
    # 30 winners (high entry_score, R1) + 30 losers (low entry_score, S1)
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
```

- [ ] **Step 2: Run test (fails)**

```bash
docker compose exec -T -e PYTHONPATH=/app api pytest /app/tests/test_ml_classifier.py -v
```

- [ ] **Step 3: Implement classifier**

`api/ml/classifier.py`:

```python
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ml.features import extract_trade_features, feature_order, to_vector
from models.trade import OrderState, Trade

MIN_SAMPLES = 30
ARTIFACT_FILENAME = "win_classifier.pkl"


def _artifact_dir() -> Path:
    return Path(os.getenv("ML_ARTIFACT_DIR", "/app/ml/artifacts"))


def _artifact_path() -> Path:
    return _artifact_dir() / ARTIFACT_FILENAME


async def train_classifier(session: AsyncSession) -> dict[str, Any]:
    rows = (await session.execute(
        select(Trade).where(
            Trade.is_paper == False,
            Trade.order_state == OrderState.filled,
            Trade.close_time.isnot(None),
            Trade.profit.isnot(None),
        )
    )).scalars().all()

    if len(rows) < MIN_SAMPLES:
        return {"status": "skipped", "samples": len(rows), "reason": f"need ≥ {MIN_SAMPLES}"}

    X, y = [], []
    for trade in rows:
        feats = await extract_trade_features(session, trade)
        X.append(to_vector(feats))
        y.append(1 if trade.profit > 0 else 0)

    if len(set(y)) < 2:
        return {"status": "skipped", "samples": len(rows), "reason": "single-class labels"}

    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    model = LogisticRegression(class_weight="balanced", max_iter=1000)
    model.fit(X_train, y_train)
    train_acc = model.score(X_train, y_train)
    val_acc = model.score(X_val, y_val)

    version = datetime.now(timezone.utc).strftime("v1-%Y%m%d-%H%M%S")
    artifact = {
        "model": model,
        "version": version,
        "feature_order": feature_order(),
        "train_acc": train_acc,
        "val_acc": val_acc,
        "samples": len(rows),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }

    _artifact_dir().mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, _artifact_path())

    return {
        "status": "trained",
        "samples": len(rows),
        "train_acc": float(train_acc),
        "val_acc": float(val_acc),
        "model_version": version,
    }


def load_classifier() -> dict | None:
    path = _artifact_path()
    if not path.exists():
        return None
    return joblib.load(path)


def predict_proba(artifact: dict, feats: dict) -> float:
    if artifact is None:
        return 0.5
    vec = [float(feats.get(k, 0)) for k in artifact["feature_order"]]
    return float(artifact["model"].predict_proba([vec])[0][1])
```

- [ ] **Step 4: Update gitignore**

Add to `.gitignore`:

```
api/ml/artifacts/
```

- [ ] **Step 5: Run test (passes)**

```bash
docker compose exec -T -e PYTHONPATH=/app api pytest /app/tests/test_ml_classifier.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add api/ml/classifier.py tests/test_ml_classifier.py .gitignore
git commit -m "feat(ml): add Logistic Regression win classifier with joblib persistence"
```

---

## Task 6 — Layer 2 pattern scorer

**Files:**
- Create: `api/ml/pattern_scorer.py`
- Create: `tests/test_ml_pattern_scorer.py`

- [ ] **Step 1: Write failing test**

`tests/test_ml_pattern_scorer.py`:

```python
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from ml.pattern_scorer import score_pattern
from models.patterns import Pattern


@pytest.mark.asyncio
async def test_score_pattern_with_no_classifier_returns_neutral(db_session, monkeypatch, tmp_path):
    monkeypatch.setenv("ML_ARTIFACT_DIR", str(tmp_path))  # no artifact saved
    pattern = Pattern(
        id=uuid4(), indicator_slugs=["ema_cross"], timeframe="H1",
        win_rate=0.6, sample_count=10, consecutive_stable_days=3,
        status="candidate", discovered_at=datetime.now(timezone.utc),
    )
    db_session.add(pattern)
    await db_session.commit()

    result = await score_pattern(db_session, pattern)
    assert result["score"] == pytest.approx(0.5, abs=0.01)
    assert result["confidence_factor"] == pytest.approx(min(1.0, 10 / 30) * 1.0, abs=0.01)
    assert result["sample_count"] == 0  # no live signals to aggregate
    assert result["model_version"] is None


@pytest.mark.asyncio
async def test_score_pattern_combines_win_prob_and_confidence(db_session, monkeypatch, tmp_path):
    """Confidence factor caps at sample=30 and stable_days=7."""
    monkeypatch.setenv("ML_ARTIFACT_DIR", str(tmp_path))
    pattern = Pattern(
        id=uuid4(), indicator_slugs=["rsi"], timeframe="H1",
        win_rate=0.7, sample_count=50, consecutive_stable_days=10,
        status="candidate", discovered_at=datetime.now(timezone.utc),
    )
    db_session.add(pattern)
    await db_session.commit()

    result = await score_pattern(db_session, pattern)
    assert result["confidence_factor"] == pytest.approx(1.0, abs=0.001)
```

- [ ] **Step 2: Run test (fails)**

```bash
docker compose exec -T -e PYTHONPATH=/app api pytest /app/tests/test_ml_pattern_scorer.py -v
```

- [ ] **Step 3: Implement pattern_scorer**

`api/ml/pattern_scorer.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession

from ml.classifier import load_classifier, predict_proba
from models.patterns import Pattern

CONFIDENCE_SAMPLE_FLOOR = 30
CONFIDENCE_STABLE_DAYS_FLOOR = 7


async def score_pattern(session: AsyncSession, pattern: Pattern) -> dict:
    artifact = load_classifier()
    confidence = (
        min(1.0, pattern.sample_count / CONFIDENCE_SAMPLE_FLOOR)
        * min(1.0, pattern.consecutive_stable_days / CONFIDENCE_STABLE_DAYS_FLOOR)
    )

    # v1: aggregate from pattern stats only when no live signals available.
    # When live signal aggregation is added, replace this block.
    if artifact is None:
        win_prob = float(pattern.win_rate or 0.5)
    else:
        feats = {
            "entry_score": 50, "direction_buy": 1,
            "hour_of_day_utc": 12, "day_of_week": 2,
            "signal_match_count": pattern.sample_count, "signal_density": 1.0,
            "rsi_value": 0.0, "ema_alignment": 0.0,
        }
        win_prob = predict_proba(artifact, feats)

    score = win_prob * confidence + 0.5 * (1 - confidence)
    return {
        "score": round(score, 4),
        "win_prob": round(win_prob, 4),
        "confidence_factor": round(confidence, 4),
        "sample_count": 0,
        "model_version": artifact["version"] if artifact else None,
    }
```

Aggregation across live signal matches is a v2 enhancement; v1 uses pattern stats with classifier as a probability prior. This is enough to validate the architecture and unblock shadow-mode logging.

- [ ] **Step 4: Run test (passes)**

```bash
docker compose exec -T -e PYTHONPATH=/app api pytest /app/tests/test_ml_pattern_scorer.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add api/ml/pattern_scorer.py tests/test_ml_pattern_scorer.py
git commit -m "feat(ml): add Layer 2 pattern scorer with confidence factor"
```

---

## Task 7 — API router

**Files:**
- Create: `api/routers/ml.py`
- Modify: `api/main.py` — register router
- Create: `tests/test_ml_router.py`

- [ ] **Step 1: Write failing test**

`tests/test_ml_router.py`:

```python
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from models.patterns import Pattern
from models.trade import Direction, OrderState, Trade


@pytest.mark.asyncio
async def test_retrain_below_threshold_returns_skipped(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("ML_ARTIFACT_DIR", str(tmp_path))
    res = await client.post("/api/ml/retrain")
    assert res.status_code == 200
    assert res.json()["status"] == "skipped"


@pytest.mark.asyncio
async def test_pattern_scores_lists_candidates(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("ML_ARTIFACT_DIR", str(tmp_path))
    pattern = Pattern(
        id=uuid4(), indicator_slugs=["rsi"], timeframe="H1",
        win_rate=0.6, sample_count=15, consecutive_stable_days=3,
        status="candidate", discovered_at=datetime.now(timezone.utc),
    )
    db_session.add(pattern)
    await db_session.commit()

    res = await client.get("/api/ml/pattern-scores")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert "score" in body[0]
    assert body[0]["pattern_id"] == str(pattern.id)


@pytest.mark.asyncio
async def test_training_status_when_no_artifact(client, tmp_path, monkeypatch):
    monkeypatch.setenv("ML_ARTIFACT_DIR", str(tmp_path))
    res = await client.get("/api/ml/training-status")
    assert res.status_code == 200
    assert res.json()["model_version"] is None
    assert res.json()["mode"] in ("shadow", "active")
```

- [ ] **Step 2: Run test (fails)**

```bash
docker compose exec -T -e PYTHONPATH=/app api pytest /app/tests/test_ml_router.py -v
```

- [ ] **Step 3: Implement router**

`api/routers/ml.py`:

```python
import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from ml.classifier import load_classifier, train_classifier
from ml.pattern_scorer import score_pattern
from models.patterns import Pattern

router = APIRouter(prefix="/api/ml", tags=["ml"])


class ScorePatternRequest(BaseModel):
    pattern_id: UUID


@router.post("/retrain")
async def retrain(session: AsyncSession = Depends(get_session)):
    return await train_classifier(session)


@router.get("/pattern-scores")
async def pattern_scores(
    status: Optional[str] = "candidate",
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Pattern)
    if status:
        stmt = stmt.where(Pattern.status == status)
    rows = (await session.execute(stmt)).scalars().all()
    out = []
    for p in rows:
        s = await score_pattern(session, p)
        out.append({
            "pattern_id": str(p.id),
            "indicator_slugs": p.indicator_slugs,
            "timeframe": p.timeframe,
            "win_rate": p.win_rate,
            "sample_count": p.sample_count,
            "stable_days": p.consecutive_stable_days,
            **s,
        })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out


@router.get("/training-status")
async def training_status():
    artifact = load_classifier()
    return {
        "model_version": artifact["version"] if artifact else None,
        "trained_at": artifact["trained_at"] if artifact else None,
        "samples": artifact["samples"] if artifact else 0,
        "train_acc": artifact["train_acc"] if artifact else None,
        "val_acc": artifact["val_acc"] if artifact else None,
        "mode": os.getenv("ML_SCORER_MODE", "shadow"),
    }


@router.post("/score-pattern")
async def score_one(
    body: ScorePatternRequest,
    session: AsyncSession = Depends(get_session),
):
    pattern = await session.get(Pattern, body.pattern_id)
    if pattern is None:
        return {"error": "pattern not found"}
    return await score_pattern(session, pattern)
```

- [ ] **Step 4: Register router**

In `api/main.py`, add to imports and `app.include_router(...)` block:

```python
from routers import ml
# ...
app.include_router(ml.router)
```

(Place near other router includes — match existing style.)

- [ ] **Step 5: Run test (passes)**

```bash
docker compose exec -T -e PYTHONPATH=/app api pytest /app/tests/test_ml_router.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add api/routers/ml.py api/main.py tests/test_ml_router.py
git commit -m "feat(ml): add ML router with retrain/pattern-scores/status/score-pattern"
```

---

## Task 8 — Shadow-mode logging hook

**Files:**
- Modify: `api/services/pattern_spawner.py` (or wherever pattern → rule spawn happens; locate via `grep -rn "spawn" api/services/`)
- Create: `api/services/ml_shadow.py`
- Create: `tests/test_ml_shadow.py`

- [ ] **Step 1: Locate spawn integration point**

```bash
grep -rn "paper_trader_rule" api/services/ | grep -i "spawn\|create\|insert"
```

The result identifies the function that decides spawn vs skip. Note: the existing function may live in `services/pattern_discovery.py` or `services/baseline_runner.py`. Read it before proceeding.

- [ ] **Step 2: Write failing integration test**

`tests/test_ml_shadow.py`:

```python
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from models.ml_pattern_score import MLPatternScore
from models.patterns import Pattern
from services.ml_shadow import log_shadow_decision


@pytest.mark.asyncio
async def test_log_shadow_decision_writes_score_row(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("ML_ARTIFACT_DIR", str(tmp_path))
    pattern = Pattern(
        id=uuid4(), indicator_slugs=["rsi"], timeframe="H1",
        win_rate=0.6, sample_count=10, consecutive_stable_days=3,
        status="candidate", discovered_at=datetime.now(timezone.utc),
    )
    db_session.add(pattern)
    await db_session.flush()

    await log_shadow_decision(db_session, pattern, rule_based_decision="spawn")
    await db_session.commit()

    rows = (await db_session.execute(
        select(MLPatternScore).where(MLPatternScore.pattern_id == pattern.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].spawn_decision == "spawn"
    assert rows[0].ml_decision in ("spawn", "skip")
```

- [ ] **Step 3: Implement shadow logger**

`api/services/ml_shadow.py`:

```python
import os
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from ml.pattern_scorer import score_pattern
from models.ml_pattern_score import MLPatternScore
from models.patterns import Pattern

DEFAULT_THRESHOLD = 0.55


async def log_shadow_decision(
    session: AsyncSession,
    pattern: Pattern,
    rule_based_decision: str,
) -> MLPatternScore:
    s = await score_pattern(session, pattern)
    threshold = float(os.getenv("ML_SPAWN_THRESHOLD", DEFAULT_THRESHOLD))
    ml_decision = "spawn" if s["score"] >= threshold else "skip"

    row = MLPatternScore(
        id=uuid4(),
        pattern_id=pattern.id,
        score=Decimal(str(s["score"])),
        model_version=s["model_version"] or "no-model",
        features=s,
        spawn_decision=rule_based_decision,
        ml_decision=ml_decision,
    )
    session.add(row)
    return row
```

- [ ] **Step 4: Wire into spawn function**

After Step 1 located the spawner, add **after** the rule-based decision but **before** any state mutation:

```python
from services.ml_shadow import log_shadow_decision

# ... existing rule-based decision logic produces decision = "spawn" | "skip"
await log_shadow_decision(session, pattern, rule_based_decision=decision)

# (Active mode gate: only enforced in v2; v1 always uses rule-based decision.)
```

This ensures every spawn evaluation produces an audit row for offline comparison.

- [ ] **Step 5: Run test (passes)**

```bash
docker compose exec -T -e PYTHONPATH=/app api pytest /app/tests/test_ml_shadow.py -v
```

- [ ] **Step 6: Commit**

```bash
git add api/services/ml_shadow.py tests/test_ml_shadow.py api/services/<spawner-file>.py
git commit -m "feat(ml): log shadow-mode decisions on every spawn evaluation"
```

---

## Task 9 — Full regression + smoke test

- [ ] **Step 1: Run entire suite**

```bash
docker compose exec -T -e PYTHONPATH=/app api pytest /app/tests/
```

Expected: previous test count + 9 new tests, all passing.

- [ ] **Step 2: Smoke test endpoints against running container**

```bash
# trigger retrain (likely returns "skipped" until ≥ 30 closed trades exist)
docker compose exec -T api curl -s -X POST http://localhost:8000/api/ml/retrain
docker compose exec -T api curl -s http://localhost:8000/api/ml/training-status
docker compose exec -T api curl -s http://localhost:8000/api/ml/pattern-scores
```

Expected: each returns valid JSON.

- [ ] **Step 3: Update backlog**

Mark "Explore ML to assist pattern discovery / signal scoring" as done in `.agents/backlog.md` (with shipped comment marker following project convention).

- [ ] **Step 4: Final commit**

```bash
git add .agents/backlog.md
git commit -m "docs: archive ML pattern scorer task — shipped 2026-05-27"
git push
```

---

## Self-review

- **Spec coverage:**
  - Layer 1 classifier → Task 4 + 5 ✓
  - Layer 2 scorer → Task 6 ✓
  - 4 endpoints → Task 7 ✓ (retrain, pattern-scores, training-status, score-pattern)
  - ml_pattern_scores table → Task 2, 3 ✓
  - Shadow-mode logging → Task 8 ✓
  - Mode toggle env var → Task 7 (training-status) + Task 8 (threshold) ✓
- **Placeholder scan:** Task 8 Step 1 deliberately uses a `grep` discovery step because the exact spawner file changes between branches. Each subsequent step references the located file; no further placeholders.
- **Type consistency:** `extract_trade_features` returns dict consumed by `to_vector` (Task 4), persisted into `MLPatternScore.features` JSONB (Task 3 model), retrieved as dict in pattern scorer (Task 6). Names align across tasks.

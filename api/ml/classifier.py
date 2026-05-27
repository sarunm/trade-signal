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

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    model = LogisticRegression(class_weight="balanced", max_iter=1000)
    model.fit(X_train, y_train)
    train_acc = model.score(X_train, y_train)
    val_acc = model.score(X_val, y_val)

    version = datetime.now(timezone.utc).strftime("v1-%Y%m%d-%H%M%S")
    artifact = {
        "model": model,
        "version": version,
        "feature_order": feature_order(),
        "train_acc": float(train_acc),
        "val_acc": float(val_acc),
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


def predict_proba(artifact: dict | None, feats: dict) -> float:
    if artifact is None:
        return 0.5
    vec = [float(feats.get(k, 0)) for k in artifact["feature_order"]]
    return float(artifact["model"].predict_proba([vec])[0][1])

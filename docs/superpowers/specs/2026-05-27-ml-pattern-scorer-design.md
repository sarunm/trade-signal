# ML Pattern Scorer — Design Spec

**Date:** 2026-05-27
**Status:** approved (pending user review)
**Backlog item:** "Explore ML to assist pattern discovery / signal scoring" (priority: low → moved to normal after this spec)

---

## 1. Goal

Add an AI ranking layer between the existing Pattern Discovery output and the Auto Paper Trader spawn step, so the system promotes the most promising patterns into paper rules instead of using only `win_rate ≥ threshold && stable_days ≥ 3`.

Initially run in **shadow mode** (predictions logged, spawn behavior unchanged) so the model can be tuned and validated while training data accumulates. Activate gating only when validation metrics meet a minimum bar.

## 2. Why now

- 110 closed real trades + 9,372 indicator signals already exist — enough to train a per-trade win classifier.
- Pattern Discovery is producing candidates faster than the current rule-based gate can evaluate them; without ranking we either spawn too few (miss opportunities) or too many (noise + virtual capital fragmentation).
- User wants the model "tuned and ready" so when more rules accumulate (currently 1 active rule, 2 trades), promotion decisions can move from heuristic to data-driven without a re-architecture.

## 3. Architecture

```
┌─────────────────────┐    ┌──────────────────────┐    ┌──────────────────┐
│ Pattern Discovery   │ →  │ ML Pattern Scorer    │ →  │ Spawn Decision   │
│ (existing)          │    │ (new — shadow mode)  │    │ (existing)       │
└─────────────────────┘    └──────────────────────┘    └──────────────────┘
                                     │
                                     ↓ uses
                           ┌──────────────────────┐
                           │ Per-trade Classifier │
                           │ (Layer 1, offline)   │
                           └──────────────────────┘
                                     ↑ trained on
                           trade_indicator_signals (9,372)
                           trades.profit (110 closed)
                           entry context (fib, near_fib_level, spread)
```

Two distinct components — kept separate so each can be replaced independently.

### Layer 1 — Per-trade Win Classifier
- **Input:** features from `trade_indicator_signals` joined with `trades` (entry_score, near_fib_level, spread proxy, time-of-day, indicator values per slug).
- **Label:** `profit > 0` (binary). Tie-breaks at exactly zero count as loss.
- **Model:** Logistic Regression first (interpretable, fast, fine for ~110 samples). Auto-upgrade to XGBoost when training set exceeds 500 closed real+paper trades.
- **Persistence:** `joblib` artifact at `api/ml/artifacts/win_classifier.pkl`. Versioned filename by training timestamp.
- **Cadence:** weekly retrain via cron-like manual trigger (`POST /api/ml/retrain`). No streaming/online learning.

### Layer 2 — Pattern Spawn Scorer
- **Input:** a candidate pattern (indicator slugs + timeframe + win_rate + sample_count + stable_days).
- **Method:**
  1. Find recent indicator signals matching the pattern's slugs+timeframe.
  2. For each match, build the same feature vector used by Layer 1 (using current market state, not historical entry).
  3. Run Layer 1 → get per-match win probability.
  4. Aggregate: `score = weighted_mean(win_prob) × confidence_factor`, where `confidence_factor = min(1, sample_count / 30) × stable_days_factor`.
- **Output:** `0..1` score per pattern, ranked.
- **Storage:** ephemeral — recomputed on demand, not persisted (cheap).

### Shadow → Active toggle
- Env: `ML_SCORER_MODE = shadow | active` (default `shadow`).
- `shadow`: scorer runs, results stored alongside existing spawn decisions for comparison.
- `active`: pattern is spawned only if `ml_score ≥ ML_SPAWN_THRESHOLD` (default 0.55) **and** existing rule-based gate passes. ML never overrides existing gate — it adds a second filter.

## 4. Data model changes

One new table to record shadow-mode predictions for later evaluation:

```sql
CREATE TABLE ml_pattern_scores (
  id              uuid PRIMARY KEY,
  pattern_id      uuid NOT NULL REFERENCES patterns(id),
  score           numeric(5,4) NOT NULL,
  model_version   varchar(40) NOT NULL,
  features        jsonb NOT NULL,          -- snapshot of feature vector for audit
  spawn_decision  varchar(20),             -- existing rule-based decision: spawn|skip
  ml_decision     varchar(20),             -- spawn|skip per ML threshold
  computed_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_ml_pattern_scores_pattern_id ON ml_pattern_scores(pattern_id);
CREATE INDEX ix_ml_pattern_scores_computed_at ON ml_pattern_scores(computed_at DESC);
```

Existing tables — no changes.

## 5. API surface

```
POST /api/ml/retrain
  → Trigger Layer 1 retrain. Body optional: { since: ISO date }.
  → Response: { status, samples, train_acc, val_acc, model_version }.

GET /api/ml/pattern-scores?status=candidate
  → List candidate patterns with current ML scores.
  → Response: [{ pattern_id, score, slugs, timeframe, would_spawn, rule_based_decision, ... }].

GET /api/ml/training-status
  → { last_trained_at, model_version, sample_count, train_acc, val_acc, mode }.

POST /api/ml/score-pattern
  → Body: pattern_id. Compute ad-hoc score (not persisted).
```

## 6. File structure

```
api/ml/
  __init__.py
  features.py        — extract feature vector from a trade or live signal
  classifier.py      — train + load + predict (Layer 1 wrapper)
  pattern_scorer.py  — Layer 2 logic
  artifacts/         — .pkl persistence (gitignored)
api/routers/
  ml.py              — endpoints listed above
api/services/
  pattern_spawn.py   — modify to consult pattern_scorer when MODE=active
tests/
  test_ml_features.py
  test_ml_classifier.py
  test_ml_pattern_scorer.py
  test_ml_router.py
api/alembic/versions/
  023_create_ml_pattern_scores.py
```

## 7. Feature vector (Layer 1 input)

Per closed trade, build:

```
{
  entry_score: int,                  # existing column
  near_fib_level: one_hot,           # R1..R3, S1..S3, PP, none
  direction: {buy: 1, sell: 0},
  spread_at_entry: float,            # current proxy: latest spread buffer at open_time
  hour_of_day_utc: int (0..23),
  day_of_week: int (0..6),
  signal_match_count: int,           # COUNT(*) FROM trade_indicator_signals WHERE matched
  indicator_signal_density: float,   # matched / total signals attached to trade
  ema_alignment_score: float,        # +1 if EMAs stacked with direction, -1 against, 0 mixed
  rsi_value: float,
  atr_norm: float,                   # ATR / open_price
}
```

All features derivable from current schema. No new columns required for v1.

## 8. Training pipeline

1. Pull all closed real trades (`is_paper=false AND close_time IS NOT NULL AND profit IS NOT NULL`) — paper trades excluded from v1 to avoid label contamination from rule-based exits.
2. For each trade, run `features.extract(trade)`.
3. Stratified 80/20 train/val split.
4. Fit Logistic Regression with class_weight='balanced'.
5. Save artifact + metrics to `api/ml/artifacts/`.
6. Write entry to `ml_training_runs` log (text file is fine for v1; promote to table if it grows).

Failure modes handled:
- < 30 closed trades → skip training, return 422 from `/api/ml/retrain`.
- Class imbalance > 90/10 → log warning, still train but flag in response.

## 9. Mode lifecycle

```
shadow (default) — predictions logged, no behavior change
   ↓ when val_acc ≥ 0.62 AND samples ≥ 200
active           — predictions filter spawn decisions
```

User flips mode via env var + container restart. No automatic promotion to active mode (explicit human gate).

## 10. Out of scope (v1)

- Online / streaming learning.
- Per-trade entry scoring (we have entry_score already).
- Exit-timing model.
- Ruin prediction.
- Frontend UI for scores (CLI/API only). UI added in a follow-up if user wants it.
- Model explainability (SHAP, etc.) — Logistic Regression coefficients are inspectable directly via `/api/ml/training-status`.

## 11. Risks

- **Sample size:** 110 trades is small; Layer 1 will likely overfit until it grows. Mitigated by shadow mode + val_acc gate before activation.
- **Distribution shift:** broker symbol changed (GOLD → GOLD#); indicator signals from older trades may have different price scale. Mitigated by feature normalization (atr_norm, no raw price).
- **Class imbalance:** if user's trades are mostly small wins (per memory, "ปิดเอง ฿500–1,000"), the model may learn "always predict win". Mitigated by class_weight='balanced' + reporting confusion matrix.
- **Feature leakage:** features must reflect entry-time state, not exit. `extract` will only use values available at `open_time`.

## 12. Success criteria (post-implementation)

- 4 endpoints respond in tests.
- Retrain produces model artifact + metrics; rerun is idempotent.
- Shadow predictions written to `ml_pattern_scores` for every new pattern that goes through spawn evaluation.
- Toggling `ML_SCORER_MODE=active` filters spawn decisions correctly per integration test.
- Zero impact on existing paper trader / pattern discovery when MODE=shadow (verified via existing test suite still passing).

---

## 13. Self-review

- **Placeholder scan:** none — every section is concrete.
- **Internal consistency:** Layer 1 (per-trade) ↔ Layer 2 (pattern aggregate) flow is consistent; feature vector matches data model; mode lifecycle matches threshold env var.
- **Scope:** single feature, single subsystem (ML scorer + 1 table + 4 endpoints + 1 router). Fits one implementation plan.
- **Ambiguity:** "weighted_mean" in Layer 2 — clarified to mean simple mean across recent matches × confidence_factor (no per-feature weighting in v1).

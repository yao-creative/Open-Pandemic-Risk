from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import IndicatorSnapshot, PipelineRunScore


@dataclass(frozen=True)
class ScoreFeatures:
    signal_count: int
    mean_value: float
    max_value: float


@dataclass
class ScoreStageResult:
    status: str
    records_in: int
    records_ok: int
    records_failed: int
    risk_value: float | None = None
    risk_band: str | None = None
    error: str | None = None


def derive_score_features(values: list[float]) -> ScoreFeatures:
    if not values:
        return ScoreFeatures(signal_count=0, mean_value=0.0, max_value=0.0)
    signal_count = len(values)
    mean_value = sum(values) / signal_count
    max_value = max(values)
    return ScoreFeatures(signal_count=signal_count, mean_value=mean_value, max_value=max_value)


def calculate_risk_value(features: ScoreFeatures) -> float:
    raw = (features.mean_value / 100.0) + (features.max_value / 200.0) + min(features.signal_count, 25) / 100.0
    return max(0.0, min(1.0, raw))


def classify_risk_band(risk_value: float) -> str:
    if risk_value >= 0.75:
        return "critical"
    if risk_value >= 0.5:
        return "high"
    if risk_value >= 0.25:
        return "medium"
    return "low"


def score_pipeline_run(db: Session, *, pipeline_run_id: int, sample_limit: int = 100) -> ScoreStageResult:
    rows = db.execute(
        select(IndicatorSnapshot.value).where(IndicatorSnapshot.value.is_not(None)).order_by(desc(IndicatorSnapshot.id)).limit(sample_limit)
    ).scalars()
    values = [float(value) for value in rows]
    features = derive_score_features(values)
    risk_value = calculate_risk_value(features)
    risk_band = classify_risk_band(risk_value)
    factors = {
        "signal_count": features.signal_count,
        "mean_value": features.mean_value,
        "max_value": features.max_value,
    }

    db.add(
        PipelineRunScore(
            pipeline_run_id=pipeline_run_id,
            scored_at=datetime.now(tz=UTC),
            risk_value=risk_value,
            risk_band=risk_band,
            factors_json=factors,
            model_version="deterministic-v1",
        )
    )
    return ScoreStageResult(
        status="ok",
        records_in=features.signal_count,
        records_ok=1,
        records_failed=0,
        risk_value=risk_value,
        risk_band=risk_band,
    )

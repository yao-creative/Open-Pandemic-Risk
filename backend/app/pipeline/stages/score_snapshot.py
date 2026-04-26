from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.models import IndicatorSnapshot, PipelineRunScore
from app.pipeline.stages.score import calculate_risk_value, classify_risk_band, derive_score_features

from .contracts import PipelineStage, StageContext, StageResult


class ScoreSnapshotStage(PipelineStage):
    name = "score_snapshot"
    required_inputs = ("snapshot_ref_id", "enrichment_pipeline_run_id")

    def run(self, context: StageContext) -> StageResult:
        snapshot_ref_id = int(context.artifacts["snapshot_ref_id"])
        target_pipeline_run_id = int(context.artifacts["enrichment_pipeline_run_id"])
        sample_limit = int(context.params.get("sample_limit") or 100)

        rows = context.db.execute(
            select(IndicatorSnapshot.value, IndicatorSnapshot.dim_json)
            .where(IndicatorSnapshot.value.is_not(None))
            .limit(sample_limit * 10)
        ).all()
        values: list[float] = []
        for value, dim_json in rows:
            row_snapshot_ref = None
            if isinstance(dim_json, dict):
                row_snapshot_ref = dim_json.get("_snapshot_ref_id")
            if row_snapshot_ref == snapshot_ref_id:
                values.append(float(value))
            if len(values) >= sample_limit:
                break

        features = derive_score_features(values)
        risk_value = calculate_risk_value(features)
        risk_band = classify_risk_band(risk_value)
        factors = {
            "signal_count": features.signal_count,
            "mean_value": features.mean_value,
            "max_value": features.max_value,
            "snapshot_ref_id": snapshot_ref_id,
        }
        context.db.add(
            PipelineRunScore(
                pipeline_run_id=target_pipeline_run_id,
                scored_at=datetime.now(tz=UTC),
                risk_value=risk_value,
                risk_band=risk_band,
                factors_json=factors,
                model_version="deterministic-v2-snapshot-scoped",
            )
        )
        context.db.commit()
        return StageResult(
            status="ok",
            metrics={"records_in": features.signal_count, "records_ok": 1, "records_failed": 0},
            artifacts={"risk_value": risk_value, "risk_band": risk_band},
        )

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import IndicatorSnapshot, MlRiskSnapshot, RecommendationResponse
from app.pipeline.stages.score import calculate_risk_value, classify_risk_band, derive_score_features


@dataclass
class RecommendationAgentResult:
    recommendation_response_id: int
    recommendation_level: str
    confidence: str
    response_text: str
    citations: list[dict[str, Any]]


class RecommendationAgentRunner:
    def _load_snapshot_values(self, db: Session, *, snapshot_ref_id: int, sample_limit: int = 100) -> list[float]:
        rows = db.execute(
            select(IndicatorSnapshot.value, IndicatorSnapshot.dim_json)
            .where(IndicatorSnapshot.value.is_not(None))
            .order_by(desc(IndicatorSnapshot.id))
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
        return values

    def _ensure_ml_snapshot(self, db: Session, *, snapshot_ref_id: int, ml_snapshot_id: int | None = None) -> MlRiskSnapshot:
        if ml_snapshot_id is not None:
            direct = db.get(MlRiskSnapshot, ml_snapshot_id)
            if direct is not None:
                return direct
        row = db.execute(
            select(MlRiskSnapshot)
            .where(MlRiskSnapshot.snapshot_ref_id == snapshot_ref_id)
            .order_by(desc(MlRiskSnapshot.id))
            .limit(1)
        ).scalar_one_or_none()
        if row is not None:
            return row

        values = self._load_snapshot_values(db, snapshot_ref_id=snapshot_ref_id)
        features = derive_score_features(values)
        risk_value = calculate_risk_value(features)
        risk_band = classify_risk_band(risk_value)
        confidence_band = "high" if risk_value >= 0.75 else ("medium" if risk_value >= 0.4 else "low")
        now = datetime.now(tz=UTC)
        row = MlRiskSnapshot(
            snapshot_ref_id=snapshot_ref_id,
            model_name="double_lasso_stub",
            model_version="v0",
            payload_json={
                "model_output": {"risk_value": risk_value, "risk_band": risk_band},
                "confidence": {"band": confidence_band, "score": round(max(0.05, min(0.95, 0.2 + risk_value)), 3)},
                "ates": {},
                "features": {
                    "signal_count": features.signal_count,
                    "mean_value": features.mean_value,
                    "max_value": features.max_value,
                },
            },
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def _draft_response(self, *, snapshot_ref_id: int, payload: dict[str, Any]) -> tuple[str, str, str, list[dict[str, Any]]]:
        model_output = payload.get("model_output") or {}
        confidence_payload = payload.get("confidence") or {}
        features = payload.get("features") or {}
        risk_band = str(model_output.get("risk_band") or "unknown")
        confidence = str(confidence_payload.get("band") or "unknown")
        signal_count = int(features.get("signal_count") or 0)
        mean_value = float(features.get("mean_value") or 0.0)

        if risk_band in {"critical", "high"}:
            recommendation_level = "urgent_response"
        elif risk_band == "medium":
            recommendation_level = "heightened_monitoring"
        elif risk_band == "low":
            recommendation_level = "routine_monitoring"
        else:
            recommendation_level = "insufficient_evidence"

        response_text = (
            f"Recommendation: {recommendation_level.replace('_', ' ')}. "
            f"Current snapshot risk is {risk_band} with {confidence} confidence. "
            f"Signal summary: {signal_count} scoped indicator values and mean {mean_value:.2f}. "
            "Use this as a decision support draft and route to human review before external publication."
        )

        citations = [
            {
                "citation_id": "S1",
                "type": "snapshot",
                "snapshot_ref_id": snapshot_ref_id,
                "path": "payload_json.model_output.risk_band",
                "value": risk_band,
            },
            {
                "citation_id": "S2",
                "type": "snapshot",
                "snapshot_ref_id": snapshot_ref_id,
                "path": "payload_json.confidence.band",
                "value": confidence,
            },
            {
                "citation_id": "S3",
                "type": "snapshot",
                "snapshot_ref_id": snapshot_ref_id,
                "path": "payload_json.features.signal_count",
                "value": signal_count,
            },
        ]
        return recommendation_level, confidence, response_text, citations

    def run(
        self,
        db: Session,
        *,
        pipeline_run_id: int,
        snapshot_ref_id: int,
        enrichment_run_id: int | None,
        ml_snapshot_id: int | None = None,
    ) -> RecommendationAgentResult:
        ml_snapshot = self._ensure_ml_snapshot(db, snapshot_ref_id=snapshot_ref_id, ml_snapshot_id=ml_snapshot_id)
        payload = ml_snapshot.payload_json if isinstance(ml_snapshot.payload_json, dict) else {}
        recommendation_level, confidence, response_text, citations = self._draft_response(
            snapshot_ref_id=snapshot_ref_id,
            payload=payload,
        )

        now = datetime.now(tz=UTC)
        row = RecommendationResponse(
            pipeline_run_id=pipeline_run_id,
            enrichment_run_id=enrichment_run_id,
            snapshot_ref_id=snapshot_ref_id,
            ml_snapshot_id=ml_snapshot.id,
            recommendation_level=recommendation_level,
            confidence=confidence,
            response_text=response_text,
            response_json={
                "recommendation_level": recommendation_level,
                "confidence": confidence,
                "response_text": response_text,
                "model_name": ml_snapshot.model_name,
                "model_version": ml_snapshot.model_version,
            },
            citations_json={"items": citations},
            created_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        return RecommendationAgentResult(
            recommendation_response_id=row.id,
            recommendation_level=recommendation_level,
            confidence=confidence,
            response_text=response_text,
            citations=citations,
        )

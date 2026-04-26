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
    confidence_score: float | None
    response_text: str
    risk_value: float | None
    risk_band: str
    risk_analytics: dict[str, Any]
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

    def _extract_risk_analytics(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_output = payload.get("model_output") or {}
        confidence_payload = payload.get("confidence") or {}
        features = payload.get("features") or {}
        ates = payload.get("ates") if isinstance(payload.get("ates"), dict) else {}

        risk_value_raw = model_output.get("risk_value")
        risk_value = float(risk_value_raw) if isinstance(risk_value_raw, (int, float)) else None
        risk_band = str(model_output.get("risk_band") or "unknown")
        confidence = str(confidence_payload.get("band") or "unknown")
        confidence_score_raw = confidence_payload.get("score")
        confidence_score = (
            float(confidence_score_raw) if isinstance(confidence_score_raw, (int, float)) else None
        )
        signal_count = int(features.get("signal_count") or 0)
        mean_value = float(features.get("mean_value") or 0.0)
        max_value = float(features.get("max_value") or 0.0)

        top_features = [
            {"name": "signal_count", "value": signal_count},
            {"name": "mean_value", "value": mean_value},
            {"name": "max_value", "value": max_value},
        ]
        ate_summary = {"count": len(ates), "keys": sorted(ates.keys())}
        return {
            "risk_value": risk_value,
            "risk_band": risk_band,
            "confidence_band": confidence,
            "confidence_score": confidence_score,
            "top_features": top_features,
            "ate_summary": ate_summary,
        }

    def _draft_response(
        self,
        *,
        snapshot_ref_id: int,
        payload: dict[str, Any],
    ) -> tuple[str, str, float | None, str, float | None, str, dict[str, Any], list[dict[str, Any]]]:
        analytics = self._extract_risk_analytics(payload)
        risk_band = str(analytics.get("risk_band") or "unknown")
        confidence = str(analytics.get("confidence_band") or "unknown")
        confidence_score = analytics.get("confidence_score")
        risk_value = analytics.get("risk_value")
        features = payload.get("features") or {}
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
        return (
            recommendation_level,
            confidence,
            confidence_score if isinstance(confidence_score, float) else None,
            response_text,
            risk_value if isinstance(risk_value, float) else None,
            risk_band,
            analytics,
            citations,
        )

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
        recommendation_level, confidence, confidence_score, response_text, risk_value, risk_band, risk_analytics, citations = self._draft_response(
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
            confidence_score=confidence_score,
            response_text=response_text,
            risk_value=risk_value,
            risk_band=risk_band,
            risk_analytics=risk_analytics,
            citations=citations,
        )

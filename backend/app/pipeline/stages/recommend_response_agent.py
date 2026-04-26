from __future__ import annotations

from app.agents.recommendation_agent import RecommendationAgentRunner
from app.models import PipelineRun

from .contracts import PipelineStage, StageContext, StageResult, StageValidationResult


class RecommendResponseAgentStage(PipelineStage):
    name = "recommend_response_agent"
    required_inputs = ("snapshot_ref_id", "enrichment_run_id")

    def validate(self, context: StageContext) -> StageValidationResult:
        base = super().validate(context)
        if not base.valid:
            return base
        snapshot_ref_id = int(context.artifacts["snapshot_ref_id"])
        snapshot_run = context.db.get(PipelineRun, snapshot_ref_id)
        if snapshot_run is None:
            return StageValidationResult(valid=False, errors=[f"snapshot_ref_id not found: {snapshot_ref_id}"])
        return StageValidationResult(valid=True)

    def run(self, context: StageContext) -> StageResult:
        snapshot_ref_id = int(context.artifacts["snapshot_ref_id"])
        enrichment_run_id = int(context.artifacts["enrichment_run_id"])
        ml_snapshot_id = context.artifacts.get("ml_snapshot_id")
        if ml_snapshot_id is None:
            ml_snapshot_id = context.params.get("ml_snapshot_id")
        runner = RecommendationAgentRunner()
        result = runner.run(
            context.db,
            pipeline_run_id=context.pipeline_run_id,
            snapshot_ref_id=snapshot_ref_id,
            enrichment_run_id=enrichment_run_id,
            ml_snapshot_id=int(ml_snapshot_id) if ml_snapshot_id is not None else None,
        )
        report = {
            "risk_analytics": result.risk_analytics,
            "recommendation": {
                "recommendation_level": result.recommendation_level,
                "response_text": result.response_text,
                "confidence": result.confidence_score if result.confidence_score is not None else result.confidence,
                "confidence_band": result.confidence,
            },
            "evidence": result.citations,
        }
        return StageResult(
            status="ok",
            metrics={"records_in": 1, "records_ok": 1, "records_failed": 0},
            artifacts={
                "recommendation_response_id": result.recommendation_response_id,
                "recommendation_level": result.recommendation_level,
                "confidence": result.confidence,
                "response_text": result.response_text,
                "risk_value": result.risk_value,
                "risk_band": result.risk_band,
                "citations": result.citations,
                "report": report,
            },
            error=None,
        )

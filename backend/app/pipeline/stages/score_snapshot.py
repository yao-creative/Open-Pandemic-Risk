from __future__ import annotations

from app.pipeline.stages.score import MODEL_VERSION, score_pipeline_run

from .contracts import PipelineStage, StageContext, StageResult


class ScoreSnapshotStage(PipelineStage):
    name = "score_snapshot"
    required_inputs = ("snapshot_ref_id",)

    def run(self, context: StageContext) -> StageResult:
        snapshot_ref_id = int(context.artifacts["snapshot_ref_id"])
        sample_limit = int(context.params.get("sample_limit") or 100)
        target_pipeline_run_id = context.pipeline_run_id
        if target_pipeline_run_id <= 0:
            target_pipeline_run_id = int(context.artifacts.get("enrichment_pipeline_run_id") or snapshot_ref_id)
        result = score_pipeline_run(
            context.db,
            pipeline_run_id=target_pipeline_run_id,
            snapshot_ref_id=snapshot_ref_id,
            sample_limit=sample_limit,
        )
        top_country = result.top_countries[0] if result.top_countries else None
        context.db.commit()
        return StageResult(
            status=result.status,
            metrics={
                "records_in": result.records_in,
                "records_ok": result.records_ok,
                "records_failed": result.records_failed,
                "countries_ranked": result.countries_ranked,
            },
            artifacts={
                "risk_score": None if top_country is None else top_country["risk_score"],
                "risk_band": None if top_country is None else top_country["risk_band"],
                "countries_ranked": result.countries_ranked,
                "top_countries": result.top_countries,
                "model_version": MODEL_VERSION,
                "result_pipeline_run_id": target_pipeline_run_id,
            },
        )

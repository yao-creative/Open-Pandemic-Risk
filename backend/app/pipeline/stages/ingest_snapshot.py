from __future__ import annotations

from app.pipeline.run_ingest import run_ingestion

from .contracts import PipelineStage, StageContext, StageResult


class IngestSnapshotStage(PipelineStage):
    name = "ingest_snapshot"

    def run(self, context: StageContext) -> StageResult:
        result = run_ingestion(context.db, context.settings)
        return StageResult(
            status="ok" if result.status in {"ok", "partial"} else "error",
            metrics={
                "records_in": result.records_in,
                "records_ok": result.records_ok,
                "records_failed": result.records_failed,
                "records_skipped": result.records_skipped,
                "codes_total": result.codes_total,
                "codes_ok": result.codes_ok,
                "codes_failed": result.codes_failed,
                "profile_name": result.profile_name,
            },
            artifacts={
                "snapshot_ref_id": result.pipeline_run_id,
                "ingest_pipeline_run_id": result.pipeline_run_id,
                "profile_name": result.profile_name,
            },
            error=None if result.status in {"ok", "partial"} else "ingestion failed",
        )

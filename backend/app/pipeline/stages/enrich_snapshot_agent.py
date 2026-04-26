from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.agents.react_agent import AgentRunner
from app.models import EnrichmentRun, PipelineRun

from .contracts import PipelineStage, StageContext, StageResult, StageValidationResult


class EnrichSnapshotAgentStage(PipelineStage):
    name = "enrich_snapshot_agent"
    required_inputs = ("snapshot_ref_id",)

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
        if not context.settings.enrichment_enabled:
            return StageResult(
                status="ok",
                metrics={"skipped": True, "reason": "enrichment disabled"},
                artifacts={
                    "enrichment_run_id": None,
                    "enrichment_pipeline_run_id": None,
                    "enrichment_status": "skipped",
                },
            )
        if not context.settings.exa_api_key:
            return StageResult(
                status="ok",
                metrics={"skipped": True, "reason": "missing exa_api_key"},
                artifacts={
                    "enrichment_run_id": None,
                    "enrichment_pipeline_run_id": None,
                    "enrichment_status": "skipped",
                },
            )

        now = datetime.now(tz=UTC)
        snapshot_ref_id = int(context.artifacts["snapshot_ref_id"])
        max_steps = int(context.params.get("max_steps") or context.settings.agent_max_steps)
        max_targets = int(context.params.get("max_targets") or context.settings.agent_max_targets)
        max_exa_calls = int(context.params.get("max_exa_calls") or context.settings.agent_max_exa_calls)

        enrich_pipeline = PipelineRun(
            pipeline_name="enrich_snapshot_agent_v1",
            started_at=now,
            finished_at=None,
            status="queued",
            records_in=0,
            records_ok=0,
            records_failed=0,
            records_skipped=0,
            error_summary=None,
            details_json=None,
        )
        context.db.add(enrich_pipeline)
        context.db.flush()

        enrichment_run = EnrichmentRun(
            pipeline_run_id=enrich_pipeline.id,
            snapshot_ref_id=snapshot_ref_id,
            idempotency_key=None,
            status="queued",
            max_steps=max_steps,
            max_targets=max_targets,
            max_exa_calls=max_exa_calls,
            steps_used=0,
            exa_calls_used=0,
            started_at=None,
            finished_at=None,
            created_at=now,
            updated_at=now,
            error_summary=None,
        )
        context.db.add(enrichment_run)
        context.db.commit()

        runner = AgentRunner(settings=context.settings)
        runner.run(context.db, enrichment_run_id=enrichment_run.id)

        latest_run = context.db.execute(select(EnrichmentRun).where(EnrichmentRun.id == enrichment_run.id)).scalar_one()
        latest_pipeline = context.db.execute(select(PipelineRun).where(PipelineRun.id == enrich_pipeline.id)).scalar_one()
        latest_pipeline.status = latest_run.status
        latest_pipeline.finished_at = latest_run.finished_at or datetime.now(tz=UTC)
        latest_pipeline.error_summary = latest_run.error_summary
        context.db.commit()

        status = "ok" if latest_run.status == "completed" else "error"
        return StageResult(
            status=status,
            metrics={
                "steps_used": latest_run.steps_used,
                "exa_calls_used": latest_run.exa_calls_used,
                "skipped": False,
            },
            artifacts={
                "enrichment_run_id": latest_run.id,
                "enrichment_pipeline_run_id": latest_run.pipeline_run_id,
                "enrichment_status": latest_run.status,
            },
            error=latest_run.error_summary if status != "ok" else None,
        )

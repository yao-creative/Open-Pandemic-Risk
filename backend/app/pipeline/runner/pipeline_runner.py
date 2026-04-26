from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import PipelineRun, PipelineRunEvent, PipelineStageRun
from app.pipeline.registry import StageRegistry
from app.pipeline.stages.contracts import StageContext, StageResult
from app.settings import Settings


STAGE_ORDER = ["ingest_snapshot", "enrich_snapshot_agent", "recommend_response_agent"]


class PipelineRunner:
    def __init__(self, *, settings: Settings, registry: StageRegistry | None = None) -> None:
        self.settings = settings
        self.registry = registry or StageRegistry()

    def create_or_get_run(self, db: Session, *, idempotency_key: str | None) -> PipelineRun:
        if idempotency_key:
            recent_runs = db.execute(
                select(PipelineRun)
                .where(PipelineRun.pipeline_name == "pipeline_full_v1")
                .order_by(desc(PipelineRun.id))
                .limit(200)
            ).scalars()
            for run in recent_runs:
                details = run.details_json or {}
                if details.get("idempotency_key") == idempotency_key:
                    return run

        now = datetime.now(tz=UTC)
        run = PipelineRun(
            pipeline_name="pipeline_full_v1",
            started_at=now,
            finished_at=None,
            status="queued",
            records_in=0,
            records_ok=0,
            records_failed=0,
            records_skipped=0,
            error_summary=None,
            details_json={
                "stage_order": STAGE_ORDER,
                "idempotency_key": idempotency_key,
                "artifacts": {},
            },
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def _append_event(self, db: Session, *, pipeline_run_id: int, stage_name: str | None, event_type: str, message: str, payload: dict[str, Any] | None = None) -> None:
        db.add(
            PipelineRunEvent(
                pipeline_run_id=pipeline_run_id,
                stage_name=stage_name,
                event_type=event_type,
                message=message,
                payload_json=payload,
                created_at=datetime.now(tz=UTC),
            )
        )

    def run(self, db: Session, *, pipeline_run_id: int, params: dict[str, Any] | None = None) -> PipelineRun:
        run = db.get(PipelineRun, pipeline_run_id)
        if run is None:
            raise ValueError(f"pipeline_run not found: {pipeline_run_id}")
        if run.status not in {"queued", "running"}:
            return run

        run.status = "running"
        run.started_at = run.started_at or datetime.now(tz=UTC)
        details = run.details_json or {}
        artifacts = dict(details.get("artifacts") or {})
        self._append_event(
            db,
            pipeline_run_id=run.id,
            stage_name=None,
            event_type="pipeline_started",
            message="pipeline execution started",
        )
        db.commit()

        try:
            for stage_name in STAGE_ORDER:
                stage = self.registry.get(stage_name)
                if stage is None:
                    raise RuntimeError(f"unknown stage: {stage_name}")

                stage_row = PipelineStageRun(
                    pipeline_run_id=run.id,
                    stage_name=stage_name,
                    status="running",
                    started_at=datetime.now(tz=UTC),
                    finished_at=None,
                    metrics_json=None,
                    artifacts_json=None,
                    error_summary=None,
                )
                db.add(stage_row)
                self._append_event(
                    db,
                    pipeline_run_id=run.id,
                    stage_name=stage_name,
                    event_type="stage_started",
                    message=f"stage started: {stage_name}",
                )
                db.commit()

                context = StageContext(
                    db=db,
                    settings=self.settings,
                    pipeline_run_id=run.id,
                    artifacts=artifacts,
                    params=params or {},
                )
                validation = stage.validate(context)
                if not validation.valid:
                    raise RuntimeError("; ".join(validation.errors))

                result = stage.run(context)
                stage_row.status = "completed" if result.status == "ok" else "failed"
                stage_row.finished_at = datetime.now(tz=UTC)
                stage_row.metrics_json = result.metrics
                stage_row.artifacts_json = result.artifacts
                stage_row.error_summary = result.error
                artifacts.update(result.artifacts)
                self._append_event(
                    db,
                    pipeline_run_id=run.id,
                    stage_name=stage_name,
                    event_type="stage_completed" if result.status == "ok" else "stage_failed",
                    message=f"stage finished: {stage_name}",
                    payload={"status": result.status, "error": result.error},
                )
                db.commit()

                if result.status != "ok":
                    raise RuntimeError(result.error or f"stage failed: {stage_name}")

            details["artifacts"] = artifacts
            run.details_json = details
            run.status = "completed"
            run.finished_at = datetime.now(tz=UTC)
            run.error_summary = None
            self._append_event(
                db,
                pipeline_run_id=run.id,
                stage_name=None,
                event_type="pipeline_completed",
                message="pipeline execution completed",
            )
            db.commit()
        except Exception as exc:
            details["artifacts"] = artifacts
            run.details_json = details
            run.status = "failed"
            run.finished_at = datetime.now(tz=UTC)
            run.error_summary = str(exc)
            self._append_event(
                db,
                pipeline_run_id=run.id,
                stage_name=None,
                event_type="pipeline_failed",
                message="pipeline execution failed",
                payload={"error": str(exc)},
            )
            db.commit()

        db.refresh(run)
        return run


def stage_result_to_stage_row_payload(result: StageResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "metrics": result.metrics,
        "artifacts": result.artifacts,
        "error": result.error,
    }

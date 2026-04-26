from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.ingest.who import ingest_who_odata
from app.models import PipelineRun
from app.pipeline.contracts import PipelineStage, StageInput, StageOutput
from app.pipeline.orchestrator import PipelineOrchestrator
from app.settings import Settings


@dataclass
class SourceRunResult:
    source: str
    records_in: int
    records_ok: int
    records_failed: int
    records_skipped: int
    error: str | None = None


@dataclass
class IngestRunResult:
    pipeline_run_id: int
    status: str
    records_in: int
    records_ok: int
    records_failed: int
    records_skipped: int
    sources: list[SourceRunResult]


class WhoIngestStage(PipelineStage):
    name = "who_odata"

    def run(self, stage_input: StageInput) -> StageOutput:
        stats = ingest_who_odata(
            stage_input.db,
            url=stage_input.settings.who_odata_url,
            timeout_seconds=stage_input.settings.ingest_http_timeout_seconds,
            item_limit=stage_input.settings.ingest_who_item_limit,
        )
        return StageOutput(
            stage=self.name,
            records_in=stats.records_in,
            records_ok=stats.records_ok,
            records_failed=stats.records_failed,
            records_skipped=stats.records_skipped,
        )


def _determine_run_status(results: list[SourceRunResult]) -> str:
    errors = [item for item in results if item.error]
    if not errors:
        return "ok"
    if len(errors) == len(results):
        return "error"
    return "partial"


def _classify_exception(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code is not None and 400 <= status_code < 500:
            return f"http_4xx: {exc}"
        return f"http_5xx: {exc}"
    if isinstance(exc, httpx.TimeoutException):
        return f"timeout_error: {exc}"
    if isinstance(exc, httpx.HTTPError):
        return f"network_error: {exc}"
    if isinstance(exc, ValueError):
        return f"parse_error: {exc}"
    return f"internal_error: {exc}"


def run_ingestion(db: Session, settings: Settings) -> IngestRunResult:
    started = datetime.now(tz=UTC)
    pipeline_run = PipelineRun(
        pipeline_name="phase1_sync_ingestion",
        started_at=started,
        finished_at=None,
        status="running",
        records_in=0,
        records_ok=0,
        records_failed=0,
        error_summary=None,
    )
    db.add(pipeline_run)
    db.flush()

    stage_input = StageInput(
        db=db,
        settings=settings,
        pipeline_name=pipeline_run.pipeline_name,
        pipeline_run_id=pipeline_run.id,
    )
    stage_outputs = PipelineOrchestrator(classify_exception=_classify_exception).run(
        stage_input=stage_input,
        stages=[WhoIngestStage()],
    )
    source_results = [
        SourceRunResult(
            source=item.stage,
            records_in=item.records_in,
            records_ok=item.records_ok,
            records_failed=item.records_failed,
            records_skipped=item.records_skipped,
            error=item.error,
        )
        for item in stage_outputs
    ]

    records_in = sum(item.records_in for item in source_results)
    records_ok = sum(item.records_ok for item in source_results)
    records_failed = sum(item.records_failed for item in source_results)
    records_skipped = sum(item.records_skipped for item in source_results)
    errors = [item.error for item in source_results if item.error]

    pipeline_run.records_in = records_in
    pipeline_run.records_ok = records_ok
    pipeline_run.records_failed = records_failed
    pipeline_run.finished_at = datetime.now(tz=UTC)
    pipeline_run.status = _determine_run_status(source_results)
    pipeline_run.error_summary = " | ".join(errors) if errors else None

    db.commit()

    return IngestRunResult(
        pipeline_run_id=pipeline_run.id,
        status=pipeline_run.status,
        records_in=records_in,
        records_ok=records_ok,
        records_failed=records_failed,
        records_skipped=records_skipped,
        sources=source_results,
    )

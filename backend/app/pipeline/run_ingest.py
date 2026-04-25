from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.ingest.promed import ingest_promed_rss
from app.ingest.who import ingest_who_odata
from app.models import PipelineRun
from app.settings import Settings


@dataclass
class SourceRunResult:
    source: str
    records_in: int
    records_ok: int
    records_failed: int
    error: str | None = None


@dataclass
class IngestRunResult:
    pipeline_run_id: int
    status: str
    records_in: int
    records_ok: int
    records_failed: int
    sources: list[SourceRunResult]


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

    source_results: list[SourceRunResult] = []

    for source_name, fn in [
        (
            "promed",
            lambda: ingest_promed_rss(
                db,
                rss_url=settings.promed_rss_url,
                timeout_seconds=settings.ingest_http_timeout_seconds,
                item_limit=settings.ingest_promed_item_limit,
            ),
        ),
        (
            "who_odata",
            lambda: ingest_who_odata(
                db,
                url=settings.who_odata_url,
                timeout_seconds=settings.ingest_http_timeout_seconds,
                item_limit=settings.ingest_who_item_limit,
            ),
        ),
    ]:
        try:
            # Isolate each source in a SAVEPOINT so DB failures don't poison the shared session.
            with db.begin_nested():
                stats = fn()
            source_results.append(
                SourceRunResult(
                    source=source_name,
                    records_in=stats.records_in,
                    records_ok=stats.records_ok,
                    records_failed=stats.records_failed,
                )
            )
        except Exception as exc:
            db.rollback()
            source_results.append(
                SourceRunResult(
                    source=source_name,
                    records_in=0,
                    records_ok=0,
                    records_failed=0,
                    error=str(exc),
                )
            )

    records_in = sum(item.records_in for item in source_results)
    records_ok = sum(item.records_ok for item in source_results)
    records_failed = sum(item.records_failed for item in source_results)
    errors = [item.error for item in source_results if item.error]

    pipeline_run.records_in = records_in
    pipeline_run.records_ok = records_ok
    pipeline_run.records_failed = records_failed
    pipeline_run.finished_at = datetime.now(tz=UTC)
    pipeline_run.status = "error" if errors else "ok"
    pipeline_run.error_summary = " | ".join(errors) if errors else None

    db.commit()

    return IngestRunResult(
        pipeline_run_id=pipeline_run.id,
        status=pipeline_run.status,
        records_in=records_in,
        records_ok=records_ok,
        records_failed=records_failed,
        sources=source_results,
    )

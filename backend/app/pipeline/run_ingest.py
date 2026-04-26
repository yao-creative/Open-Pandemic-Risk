from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.ingest.who import ingest_who_odata
from app.ingest.who_profiles import get_who_surveillance_profile
from app.models import PipelineRun
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
class CodeRunResult:
    code: str
    category: str
    status: str
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
    profile_name: str
    codes_total: int
    codes_ok: int
    codes_failed: int
    code_results: list[CodeRunResult]
    sources: list[SourceRunResult]


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


def _build_source_result_from_codes(code_results: list[CodeRunResult]) -> SourceRunResult:
    return SourceRunResult(
        source="who_odata",
        records_in=sum(item.records_in for item in code_results),
        records_ok=sum(item.records_ok for item in code_results),
        records_failed=sum(item.records_failed for item in code_results),
        records_skipped=sum(item.records_skipped for item in code_results),
        error=None,
    )


def _serialize_details(
    profile_name: str,
    code_results: list[CodeRunResult],
    source_results: list[SourceRunResult],
) -> dict:
    codes_failed = len([item for item in code_results if item.error])
    return {
        "profile_name": profile_name,
        "codes_total": len(code_results),
        "codes_ok": len(code_results) - codes_failed,
        "codes_failed": codes_failed,
        "code_results": [asdict(item) for item in code_results],
        "sources": [asdict(item) for item in source_results],
    }


def result_from_pipeline_run(pipeline_run: PipelineRun) -> IngestRunResult:
    details = pipeline_run.details_json or {}
    profile_name = str(details.get("profile_name") or "who_surveillance_mvp_v1")
    code_results = [CodeRunResult(**item) for item in details.get("code_results", []) if isinstance(item, dict)]
    source_results = [SourceRunResult(**item) for item in details.get("sources", []) if isinstance(item, dict)]
    if not source_results:
        source_results = [
            SourceRunResult(
                source="who_odata",
                records_in=pipeline_run.records_in,
                records_ok=pipeline_run.records_ok,
                records_failed=pipeline_run.records_failed,
                records_skipped=pipeline_run.records_skipped,
                error=pipeline_run.error_summary,
            )
        ]

    codes_total = int(details.get("codes_total", len(code_results)))
    codes_failed = int(details.get("codes_failed", len([item for item in code_results if item.error])))
    codes_ok = int(details.get("codes_ok", max(codes_total - codes_failed, 0)))

    return IngestRunResult(
        pipeline_run_id=pipeline_run.id,
        status=pipeline_run.status,
        records_in=pipeline_run.records_in,
        records_ok=pipeline_run.records_ok,
        records_failed=pipeline_run.records_failed,
        records_skipped=pipeline_run.records_skipped,
        profile_name=profile_name,
        codes_total=codes_total,
        codes_ok=codes_ok,
        codes_failed=codes_failed,
        code_results=code_results,
        sources=source_results,
    )


def run_ingestion(db: Session, settings: Settings) -> IngestRunResult:
    started = datetime.now(tz=UTC)
    profile_name, profile_codes = get_who_surveillance_profile()
    pipeline_run = PipelineRun(
        pipeline_name="who_surveillance_sync_v1",
        started_at=started,
        finished_at=None,
        status="running",
        records_in=0,
        records_ok=0,
        records_failed=0,
        records_skipped=0,
        error_summary=None,
        details_json=None,
    )
    db.add(pipeline_run)
    db.flush()

    base = settings.who_odata_base_url.rstrip("/")
    code_results: list[CodeRunResult] = []

    for item in profile_codes:
        url = f"{base}/{item.code}"
        try:
            with db.begin_nested():
                stats = ingest_who_odata(
                    db,
                    url=url,
                    timeout_seconds=settings.ingest_http_timeout_seconds,
                    item_limit=settings.ingest_who_item_limit,
                    profile_name=profile_name,
                    profile_category=item.category,
                    snapshot_ref_id=pipeline_run.id,
                )
            code_results.append(
                CodeRunResult(
                    code=item.code,
                    category=item.category,
                    status="ok",
                    records_in=stats.records_in,
                    records_ok=stats.records_ok,
                    records_failed=stats.records_failed,
                    records_skipped=stats.records_skipped,
                    error=None,
                )
            )
        except Exception as exc:
            # begin_nested() already rolled back this code's savepoint; keep outer transaction active
            code_results.append(
                CodeRunResult(
                    code=item.code,
                    category=item.category,
                    status="error",
                    records_in=0,
                    records_ok=0,
                    records_failed=0,
                    records_skipped=0,
                    error=_classify_exception(exc),
                )
            )

    source_results = [_build_source_result_from_codes(code_results)]
    failed_codes = len([item for item in code_results if item.error])

    pipeline_run.records_in = sum(item.records_in for item in code_results)
    pipeline_run.records_ok = sum(item.records_ok for item in code_results)
    pipeline_run.records_failed = sum(item.records_failed for item in code_results)
    pipeline_run.records_skipped = sum(item.records_skipped for item in code_results)
    pipeline_run.finished_at = datetime.now(tz=UTC)
    if failed_codes == 0:
        pipeline_run.status = "ok"
    elif failed_codes == len(code_results):
        pipeline_run.status = "error"
    else:
        pipeline_run.status = "partial"

    error_messages = [item.error for item in code_results if item.error]
    pipeline_run.error_summary = " | ".join(error_messages) if error_messages else None
    pipeline_run.details_json = _serialize_details(profile_name, code_results, source_results)

    db.commit()

    return result_from_pipeline_run(pipeline_run)

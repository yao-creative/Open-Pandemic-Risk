from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.clients import ExaClient
from app.models import ExaCitation
from app.settings import Settings


@dataclass
class EnrichWithExaResult:
    status: str
    citations_saved: int
    error: str | None = None


def _classify_exa_exception(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_error: {exc}"
    if isinstance(exc, httpx.TimeoutException):
        return f"timeout_error: {exc}"
    if isinstance(exc, httpx.HTTPError):
        return f"network_error: {exc}"
    return f"internal_error: {exc}"


def enrich_with_exa(db: Session, *, settings: Settings, pipeline_run_id: int, query: str | None = None) -> EnrichWithExaResult:
    if not settings.exa_api_key:
        return EnrichWithExaResult(status="skipped", citations_saved=0)

    final_query = query or settings.exa_default_query
    client = ExaClient(
        api_url=settings.exa_api_url,
        api_key=settings.exa_api_key,
        timeout_seconds=settings.ingest_http_timeout_seconds,
    )
    try:
        results = client.search(query=final_query, num_results=settings.exa_num_results)
    except Exception as exc:
        return EnrichWithExaResult(
            status="error",
            citations_saved=0,
            error=_classify_exa_exception(exc),
        )

    now = datetime.now(tz=UTC)
    for result in results:
        db.add(
            ExaCitation(
                pipeline_run_id=pipeline_run_id,
                url=result.url,
                title=result.title,
                snippet=result.snippet,
                query=final_query,
                created_at=now,
            )
        )
    return EnrichWithExaResult(status="ok", citations_saved=len(results))

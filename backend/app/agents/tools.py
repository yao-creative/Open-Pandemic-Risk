from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.policies import allowed_tables, enforce_limit
from app.clients import ExaClient
from app.models import AgentToolAudit, IndicatorSnapshot, PipelineRun, SourceRegistry
from app.settings import Settings

TABLE_MODELS = {
    "pipeline_run": PipelineRun,
    "indicator_snapshot": IndicatorSnapshot,
    "source_registry": SourceRegistry,
}


def _read_run_results(db: Session, *, run_id: int) -> dict[str, Any]:
    run = db.get(PipelineRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"pipeline_run not found: {run_id}")
    return {
        "id": run.id,
        "pipeline_name": run.pipeline_name,
        "status": run.status,
        "records_in": run.records_in,
        "records_ok": run.records_ok,
        "records_failed": run.records_failed,
        "error_summary": run.error_summary,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def _explore_db_readonly(
    db: Session,
    *,
    table: str,
    filters: dict[str, Any],
    limit: int | None,
    settings: Settings,
) -> dict[str, Any]:
    allowed = allowed_tables(settings)
    if table not in allowed:
        raise HTTPException(status_code=400, detail=f"table is not allowed: {table}")
    model = TABLE_MODELS.get(table)
    if model is None:
        raise HTTPException(status_code=400, detail=f"unsupported table: {table}")

    query = select(model)
    for column_name, value in (filters or {}).items():
        column = getattr(model, column_name, None)
        if column is None:
            raise HTTPException(status_code=400, detail=f"invalid filter column: {column_name}")
        query = query.where(column == value)

    bounded_limit = enforce_limit(requested=limit, max_limit=settings.agent_row_limit)
    rows = db.execute(query.limit(bounded_limit)).scalars().all()
    results: list[dict[str, Any]] = []
    for row in rows:
        row_payload = {
            key: value
            for key, value in vars(row).items()
            if not key.startswith("_")
        }
        for key, value in row_payload.items():
            if isinstance(value, datetime):
                row_payload[key] = value.isoformat()
        results.append(row_payload)
    return {"table": table, "count": len(results), "rows": results}


def _search_exa(settings: Settings, *, query: str, num_results: int | None) -> dict[str, Any]:
    if not settings.exa_api_key:
        raise HTTPException(status_code=400, detail="exa_api_key is not configured")
    bounded_limit = enforce_limit(requested=num_results, max_limit=settings.agent_row_limit)
    client = ExaClient(
        api_url=settings.exa_api_url,
        api_key=settings.exa_api_key,
        timeout_seconds=settings.agent_query_timeout_seconds,
    )
    try:
        results = client.search(query=query, num_results=bounded_limit)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"search_exa upstream error: {exc}") from exc
    return {
        "query": query,
        "count": len(results),
        "results": [{"url": item.url, "title": item.title, "snippet": item.snippet} for item in results],
    }


def _write_audit_log(
    db: Session,
    *,
    tool_name: str,
    args: dict[str, Any],
    started: float,
    success: bool,
    error_summary: str | None,
) -> None:
    elapsed = int((perf_counter() - started) * 1000)
    db.add(
        AgentToolAudit(
            tool_name=tool_name,
            requested_at=datetime.now(tz=UTC),
            duration_ms=elapsed,
            success=success,
            args_json=args,
            error_summary=error_summary,
        )
    )
    db.commit()


def execute_agent_tool(db: Session, *, settings: Settings, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    started = perf_counter()
    try:
        if tool == "read_run_results":
            result = _read_run_results(db, run_id=int(args["run_id"]))
        elif tool == "explore_db_readonly":
            result = _explore_db_readonly(
                db,
                table=str(args["table"]),
                filters=args.get("filters") or {},
                limit=args.get("limit"),
                settings=settings,
            )
        elif tool == "search_exa":
            result = _search_exa(
                settings,
                query=str(args["query"]),
                num_results=args.get("num_results"),
            )
        else:
            raise HTTPException(status_code=400, detail=f"unknown tool: {tool}")
        _write_audit_log(
            db,
            tool_name=tool,
            args=args,
            started=started,
            success=True,
            error_summary=None,
        )
        return result
    except HTTPException as exc:
        _write_audit_log(
            db,
            tool_name=tool,
            args=args,
            started=started,
            success=False,
            error_summary=str(exc.detail),
        )
        raise

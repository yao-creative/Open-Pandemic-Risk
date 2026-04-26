from dataclasses import asdict
from datetime import UTC, datetime
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .agents.react_agent import AgentRunner
from .azure_client import check_azure_ready
from .db import check_db_ready, get_db_session, get_session_local, init_db
from .models import EnrichmentReport, EnrichmentRun, PipelineRun, PipelineRunScore
from .pipeline.run_ingest import result_from_pipeline_run, run_ingestion
from .pipeline.stages.score import score_pipeline_run
from .schemas import (
    CodeRunResultSchema,
    EnrichmentRunListItem,
    EnrichmentRunListResponse,
    EnrichmentRunStatusResponse,
    IngestRunResponse,
    PipelineRunDetailResponse,
    ScoreRunResponse,
    SnapshotEnrichRequest,
    SnapshotEnrichResponse,
    SourceRunResultSchema,
)
from .settings import get_settings

app = FastAPI(title="biohack-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    db_ok, db_error = check_db_ready()
    azure_ok, azure_error = check_azure_ready()

    checks = {
        "db": "ok" if db_ok else "error",
        "azure_openai": "ok" if azure_ok else "error",
    }
    details = [msg for msg in [db_error, azure_error] if msg]

    payload = {
        "ready": db_ok and azure_ok,
        "checks": checks,
        "details": details,
    }

    if payload["ready"]:
        return payload
    return JSONResponse(status_code=503, content=payload)


@app.post("/ingest/run", response_model=IngestRunResponse)
def ingest_run(db: Session = Depends(get_db_session)) -> IngestRunResponse:
    result = run_ingestion(db, get_settings())
    return IngestRunResponse(
        pipeline_run_id=result.pipeline_run_id,
        status=result.status,
        records_in=result.records_in,
        records_ok=result.records_ok,
        records_failed=result.records_failed,
        records_skipped=result.records_skipped,
        profile_name=result.profile_name,
        codes_total=result.codes_total,
        codes_ok=result.codes_ok,
        codes_failed=result.codes_failed,
        sources=[SourceRunResultSchema(**asdict(item)) for item in result.sources],
        code_results=[CodeRunResultSchema(**asdict(item)) for item in result.code_results],
    )


@app.get("/runs/{pipeline_run_id}", response_model=PipelineRunDetailResponse)
def get_run(pipeline_run_id: int, db: Session = Depends(get_db_session)) -> PipelineRunDetailResponse:
    pipeline_run = db.get(PipelineRun, pipeline_run_id)
    if pipeline_run is None:
        raise HTTPException(status_code=404, detail="pipeline run not found")
    result = result_from_pipeline_run(pipeline_run)
    return PipelineRunDetailResponse(
        pipeline_run_id=result.pipeline_run_id,
        pipeline_name=pipeline_run.pipeline_name,
        started_at=pipeline_run.started_at,
        finished_at=pipeline_run.finished_at,
        status=result.status,
        records_in=result.records_in,
        records_ok=result.records_ok,
        records_failed=result.records_failed,
        records_skipped=result.records_skipped,
        error_summary=pipeline_run.error_summary,
        profile_name=result.profile_name,
        codes_total=result.codes_total,
        codes_ok=result.codes_ok,
        codes_failed=result.codes_failed,
        sources=[SourceRunResultSchema(**asdict(item)) for item in result.sources],
        code_results=[CodeRunResultSchema(**asdict(item)) for item in result.code_results],
    )


def _run_snapshot_enrichment_background(enrichment_run_id: int) -> None:
    session_local = get_session_local()
    with session_local() as db:
        runner = AgentRunner(settings=get_settings())
        runner.run(db, enrichment_run_id=enrichment_run_id)


@app.post("/agent/enrich", response_model=SnapshotEnrichResponse)
@app.post("/agent/snapshot-enrich", response_model=SnapshotEnrichResponse)
def agent_snapshot_enrich(
    payload: SnapshotEnrichRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
) -> SnapshotEnrichResponse:
    settings = get_settings()

    snapshot_ref_id = payload.snapshot_id
    if snapshot_ref_id is None:
        snapshot_ref_id = db.execute(
            select(PipelineRun.id)
            .where(PipelineRun.pipeline_name == "phase1_sync_ingestion")
            .order_by(desc(PipelineRun.id))
            .limit(1)
        ).scalar_one_or_none()
    if snapshot_ref_id is None:
        raise HTTPException(status_code=400, detail="no compatible snapshot found (phase1_sync_ingestion)")

    if payload.idempotency_key:
        existing_query = select(EnrichmentRun).where(EnrichmentRun.idempotency_key == payload.idempotency_key)
        if snapshot_ref_id is not None:
            existing_query = existing_query.where(EnrichmentRun.snapshot_ref_id == snapshot_ref_id)
        existing = db.execute(existing_query.order_by(desc(EnrichmentRun.id)).limit(1)).scalar_one_or_none()
        if existing is not None:
            return SnapshotEnrichResponse(
                enrichment_run_id=existing.id,
                pipeline_run_id=existing.pipeline_run_id,
                snapshot_ref_id=existing.snapshot_ref_id,
                status=existing.status,
            )

    now = datetime.now(tz=UTC)
    pipeline_run = PipelineRun(
        pipeline_name="agent_enrich",
        started_at=now,
        finished_at=None,
        status="queued",
        records_in=0,
        records_ok=0,
        records_failed=0,
        error_summary=None,
    )
    db.add(pipeline_run)
    db.flush()

    enrichment_run = EnrichmentRun(
        pipeline_run_id=pipeline_run.id,
        snapshot_ref_id=snapshot_ref_id,
        idempotency_key=payload.idempotency_key,
        status="queued",
        max_steps=settings.agent_max_steps,
        max_targets=settings.agent_max_targets,
        max_exa_calls=settings.agent_max_exa_calls,
        steps_used=0,
        exa_calls_used=0,
        started_at=None,
        finished_at=None,
        created_at=now,
        updated_at=now,
        error_summary=None,
    )
    db.add(enrichment_run)
    db.commit()

    background_tasks.add_task(_run_snapshot_enrichment_background, enrichment_run.id)
    return SnapshotEnrichResponse(
        enrichment_run_id=enrichment_run.id,
        pipeline_run_id=enrichment_run.pipeline_run_id,
        snapshot_ref_id=enrichment_run.snapshot_ref_id,
        status=enrichment_run.status,
    )


@app.get("/agent/runs", response_model=EnrichmentRunListResponse)
def list_agent_runs(
    db: Session = Depends(get_db_session),
    limit: int = 20,
    offset: int = 0,
    status: Literal["queued", "running", "completed", "failed"] | None = None,
    snapshot_ref_id: int | None = None,
    pipeline_run_id: int | None = None,
    has_report: bool | None = None,
    order_by: Literal["created_at", "updated_at", "id"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
) -> EnrichmentRunListResponse:
    bounded_limit = min(max(limit, 1), 100)
    bounded_offset = max(offset, 0)

    query = select(EnrichmentRun)
    count_query = select(func.count(EnrichmentRun.id))

    if status is not None:
        query = query.where(EnrichmentRun.status == status)
        count_query = count_query.where(EnrichmentRun.status == status)
    if snapshot_ref_id is not None:
        query = query.where(EnrichmentRun.snapshot_ref_id == snapshot_ref_id)
        count_query = count_query.where(EnrichmentRun.snapshot_ref_id == snapshot_ref_id)
    if pipeline_run_id is not None:
        query = query.where(EnrichmentRun.pipeline_run_id == pipeline_run_id)
        count_query = count_query.where(EnrichmentRun.pipeline_run_id == pipeline_run_id)
    if has_report is not None:
        report_exists = select(EnrichmentReport.id).where(EnrichmentReport.enrichment_run_id == EnrichmentRun.id).exists()
        query = query.where(report_exists if has_report else ~report_exists)
        count_query = count_query.where(report_exists if has_report else ~report_exists)

    sort_column = {
        "created_at": EnrichmentRun.created_at,
        "updated_at": EnrichmentRun.updated_at,
        "id": EnrichmentRun.id,
    }[order_by]
    query = query.order_by(sort_column.asc() if order == "asc" else sort_column.desc())
    rows = db.execute(query.limit(bounded_limit).offset(bounded_offset)).scalars().all()
    total = int(db.execute(count_query).scalar_one())

    items = [
        EnrichmentRunListItem(
            enrichment_run_id=row.id,
            pipeline_run_id=row.pipeline_run_id,
            snapshot_ref_id=row.snapshot_ref_id,
            status=row.status,
            created_at=row.created_at.isoformat(),
            updated_at=row.updated_at.isoformat(),
            started_at=row.started_at.isoformat() if row.started_at else None,
            finished_at=row.finished_at.isoformat() if row.finished_at else None,
        )
        for row in rows
    ]
    return EnrichmentRunListResponse(items=items, total=total, limit=bounded_limit, offset=bounded_offset)


@app.get("/agent/runs/{enrichment_run_id}", response_model=EnrichmentRunStatusResponse)
def get_agent_run(enrichment_run_id: int, db: Session = Depends(get_db_session)) -> EnrichmentRunStatusResponse:
    run = db.get(EnrichmentRun, enrichment_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"enrichment_run not found: {enrichment_run_id}")

    report = db.execute(
        select(EnrichmentReport).where(EnrichmentReport.enrichment_run_id == enrichment_run_id).limit(1)
    ).scalar_one_or_none()
    return EnrichmentRunStatusResponse(
        enrichment_run_id=run.id,
        pipeline_run_id=run.pipeline_run_id,
        snapshot_ref_id=run.snapshot_ref_id,
        status=run.status,
        steps_used=run.steps_used,
        exa_calls_used=run.exa_calls_used,
        max_steps=run.max_steps,
        max_exa_calls=run.max_exa_calls,
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        error_summary=run.error_summary,
        report=report.summary_json if report else None,
    )


@app.post("/agent/runs/{enrichment_run_id}/score", response_model=ScoreRunResponse)
def score_agent_run(enrichment_run_id: int, db: Session = Depends(get_db_session)) -> ScoreRunResponse:
    run = db.get(EnrichmentRun, enrichment_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"enrichment_run not found: {enrichment_run_id}")
    if run.status != "completed":
        raise HTTPException(status_code=400, detail=f"enrichment_run is not completed: {run.status}")

    score_result = score_pipeline_run(db, pipeline_run_id=run.pipeline_run_id)
    pipeline_run = db.get(PipelineRun, run.pipeline_run_id)
    if pipeline_run is not None:
        pipeline_run.status = "scored"
    db.commit()

    score_row = db.execute(
        select(PipelineRunScore).where(PipelineRunScore.pipeline_run_id == run.pipeline_run_id).order_by(desc(PipelineRunScore.id)).limit(1)
    ).scalar_one()
    return ScoreRunResponse(
        enrichment_run_id=run.id,
        pipeline_run_id=run.pipeline_run_id,
        status=score_result.status,
        risk_value=float(score_row.risk_value),
        risk_band=score_row.risk_band,
    )

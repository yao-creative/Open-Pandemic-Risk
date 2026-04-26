from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db_session, get_session_local
from app.models import PipelineRun, PipelineRunEvent, PipelineStageRun
from app.pipeline.runner.pipeline_runner import STAGE_ORDER, PipelineRunner
from app.schemas import (
    PipelineEventListResponse,
    PipelineEventSchema,
    PipelineRunCreateRequest,
    PipelineRunCreateResponse,
    PipelineRunStatusResponse,
    PipelineStageRunSchema,
)
from app.settings import get_settings

router = APIRouter(prefix="/pipeline", tags=["pipeline"])
logger = logging.getLogger("biohack.pipeline.api")


def _run_pipeline_background(pipeline_run_id: int) -> None:
    session_local = get_session_local()
    with session_local() as db:
        logger.info("pipeline_background_start pipeline_run_id=%s", pipeline_run_id)
        runner = PipelineRunner(settings=get_settings())
        runner.run(db, pipeline_run_id=pipeline_run_id)
        logger.info("pipeline_background_finish pipeline_run_id=%s", pipeline_run_id)


@router.post("/run", response_model=PipelineRunCreateResponse)
def run_pipeline(
    payload: PipelineRunCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
) -> PipelineRunCreateResponse:
    logger.info("pipeline_run_requested idempotency_key=%s", payload.idempotency_key or "-")
    runner = PipelineRunner(settings=get_settings())
    run = runner.create_or_get_run(db, idempotency_key=payload.idempotency_key)
    if run.status == "queued":
        background_tasks.add_task(_run_pipeline_background, run.id)
    logger.info("pipeline_run_response pipeline_run_id=%s status=%s", run.id, run.status)
    return PipelineRunCreateResponse(
        pipeline_run_id=run.id,
        status=run.status,
        stage_order=STAGE_ORDER,
    )


@router.get("/runs/{pipeline_run_id}", response_model=PipelineRunStatusResponse)
def get_pipeline_run(pipeline_run_id: int, db: Session = Depends(get_db_session)) -> PipelineRunStatusResponse:
    logger.info("pipeline_run_lookup pipeline_run_id=%s", pipeline_run_id)
    run = db.get(PipelineRun, pipeline_run_id)
    if run is None or run.pipeline_name != "pipeline_full_v1":
        raise HTTPException(status_code=404, detail="pipeline run not found")
    stage_rows = db.execute(
        select(PipelineStageRun).where(PipelineStageRun.pipeline_run_id == run.id).order_by(PipelineStageRun.id.asc())
    ).scalars().all()
    details = run.details_json or {}
    return PipelineRunStatusResponse(
        pipeline_run_id=run.id,
        pipeline_name=run.pipeline_name,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error_summary=run.error_summary,
        artifacts=dict(details.get("artifacts") or {}),
        stage_runs=[
            PipelineStageRunSchema(
                id=item.id,
                stage_name=item.stage_name,
                status=item.status,
                started_at=item.started_at,
                finished_at=item.finished_at,
                metrics=item.metrics_json,
                artifacts=item.artifacts_json,
                error_summary=item.error_summary,
            )
            for item in stage_rows
        ],
    )


@router.get("/runs/{pipeline_run_id}/events", response_model=PipelineEventListResponse)
def get_pipeline_run_events(pipeline_run_id: int, db: Session = Depends(get_db_session)) -> PipelineEventListResponse:
    logger.info("pipeline_events_lookup pipeline_run_id=%s", pipeline_run_id)
    run = db.get(PipelineRun, pipeline_run_id)
    if run is None or run.pipeline_name != "pipeline_full_v1":
        raise HTTPException(status_code=404, detail="pipeline run not found")
    rows = db.execute(
        select(PipelineRunEvent).where(PipelineRunEvent.pipeline_run_id == pipeline_run_id).order_by(PipelineRunEvent.id.asc())
    ).scalars().all()
    return PipelineEventListResponse(
        pipeline_run_id=pipeline_run_id,
        events=[
            PipelineEventSchema(
                id=row.id,
                stage_name=row.stage_name,
                event_type=row.event_type,
                message=row.message,
                payload=row.payload_json,
                created_at=row.created_at,
            )
            for row in rows
        ],
    )

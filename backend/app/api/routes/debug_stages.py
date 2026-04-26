from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db_session
from app.models import PipelineRun
from app.pipeline.registry import StageRegistry
from app.pipeline.stages.contracts import StageContext
from app.schemas import (
    DebugStageRunRequest,
    DebugStageRunResponse,
    DebugStageValidationResponse,
    StageCatalogItem,
    StageCatalogResponse,
)
from app.settings import get_settings

router = APIRouter(prefix="/debug/stages", tags=["debug-stages"])
logger = logging.getLogger("biohack.debug-stages")


def _build_context(db: Session, stage_name: str, payload: DebugStageRunRequest) -> StageContext:
    artifacts: dict[str, int] = {}
    if payload.snapshot_ref_id is not None:
        artifacts["snapshot_ref_id"] = payload.snapshot_ref_id
    if payload.enrichment_pipeline_run_id is not None:
        artifacts["enrichment_pipeline_run_id"] = payload.enrichment_pipeline_run_id

    params = payload.model_dump(exclude_none=True)
    return StageContext(
        db=db,
        settings=get_settings(),
        pipeline_run_id=0,
        artifacts=artifacts,
        params=params,
    )


@router.get("", response_model=StageCatalogResponse)
def list_stages() -> StageCatalogResponse:
    registry = StageRegistry()
    return StageCatalogResponse(
        stages=[
            StageCatalogItem(name=stage.name, required_inputs=list(stage.required_inputs))
            for stage in registry.list_stages()
        ]
    )


@router.post("/{stage_name}/validate", response_model=DebugStageValidationResponse)
def validate_stage(
    stage_name: str,
    payload: DebugStageRunRequest,
    db: Session = Depends(get_db_session),
) -> DebugStageValidationResponse:
    logger.info("debug_stage_validate_requested stage=%s payload=%s", stage_name, payload.model_dump(exclude_none=True))
    stage = StageRegistry().get(stage_name)
    if stage is None:
        raise HTTPException(status_code=404, detail=f"unknown stage: {stage_name}")
    context = _build_context(db, stage_name, payload)
    validation = stage.validate(context)
    logger.info("debug_stage_validate_result stage=%s valid=%s errors=%s", stage_name, validation.valid, validation.errors)
    return DebugStageValidationResponse(stage=stage_name, valid=validation.valid, errors=validation.errors)


@router.post("/{stage_name}/run", response_model=DebugStageRunResponse)
def run_stage(
    stage_name: str,
    payload: DebugStageRunRequest,
    db: Session = Depends(get_db_session),
) -> DebugStageRunResponse:
    logger.info("debug_stage_run_requested stage=%s payload=%s", stage_name, payload.model_dump(exclude_none=True))
    stage = StageRegistry().get(stage_name)
    if stage is None:
        raise HTTPException(status_code=404, detail=f"unknown stage: {stage_name}")

    context = _build_context(db, stage_name, payload)
    validation = stage.validate(context)
    if not validation.valid:
        raise HTTPException(status_code=400, detail="; ".join(validation.errors))

    if stage_name == "score_snapshot" and payload.enrichment_pipeline_run_id is None:
        debug_run = PipelineRun(
            pipeline_name="debug_score_stage_v1",
            started_at=datetime.now(tz=UTC),
            finished_at=None,
            status="running",
            records_in=0,
            records_ok=0,
            records_failed=0,
            records_skipped=0,
            error_summary=None,
            details_json=None,
        )
        db.add(debug_run)
        db.flush()
        context.artifacts["enrichment_pipeline_run_id"] = debug_run.id
        db.commit()

    result = stage.run(context)
    logger.info("debug_stage_run_result stage=%s status=%s error=%s", stage_name, result.status, result.error)
    return DebugStageRunResponse(
        stage=stage_name,
        status=result.status,
        metrics=result.metrics,
        artifacts=result.artifacts,
        error=result.error,
    )

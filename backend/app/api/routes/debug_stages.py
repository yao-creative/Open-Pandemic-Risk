from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db_session
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


def _build_context(db: Session, stage_name: str, payload: DebugStageRunRequest) -> StageContext:
    artifacts: dict[str, int] = {}
    if payload.snapshot_ref_id is not None:
        artifacts["snapshot_ref_id"] = payload.snapshot_ref_id
    if payload.enrichment_run_id is not None:
        artifacts["enrichment_run_id"] = payload.enrichment_run_id

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
    stage = StageRegistry().get(stage_name)
    if stage is None:
        raise HTTPException(status_code=404, detail=f"unknown stage: {stage_name}")
    context = _build_context(db, stage_name, payload)
    validation = stage.validate(context)
    return DebugStageValidationResponse(stage=stage_name, valid=validation.valid, errors=validation.errors)


@router.post("/{stage_name}/run", response_model=DebugStageRunResponse)
def run_stage(
    stage_name: str,
    payload: DebugStageRunRequest,
    db: Session = Depends(get_db_session),
) -> DebugStageRunResponse:
    stage = StageRegistry().get(stage_name)
    if stage is None:
        raise HTTPException(status_code=404, detail=f"unknown stage: {stage_name}")

    context = _build_context(db, stage_name, payload)
    validation = stage.validate(context)
    if not validation.valid:
        raise HTTPException(status_code=400, detail="; ".join(validation.errors))

    result = stage.run(context)
    return DebugStageRunResponse(
        stage=stage_name,
        status=result.status,
        metrics=result.metrics,
        artifacts=result.artifacts,
        error=result.error,
    )

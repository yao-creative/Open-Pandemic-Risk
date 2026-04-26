from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db import get_db_session, get_session_local
from app.models import CountryRiskResult, PipelineRun, PipelineRunEvent, PipelineStageRun
from app.pipeline.runner.pipeline_runner import STAGE_ORDER, PipelineRunner
from app.schemas import (
    CountryRiskDetailSchema,
    CountryRiskRowSchema,
    ContributorSchema,
    PipelineCountryDetailResponse,
    PipelineCountryResultsResponse,
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


def _is_retryable_sqlite_lock(exc: OperationalError) -> bool:
    return "database is locked" in str(exc).lower()


def _get_pipeline_run_or_404(db: Session, pipeline_run_id: int) -> PipelineRun:
    run = db.get(PipelineRun, pipeline_run_id)
    if run is None or run.pipeline_name != "pipeline_full_v1":
        raise HTTPException(status_code=404, detail="pipeline run not found")
    return run


def _serialize_contributors(items: list[dict] | None, *, limit: int | None = None) -> list[ContributorSchema]:
    rows = items or []
    if limit is not None:
        rows = rows[:limit]
    return [
        ContributorSchema(
            indicator_code=str(item.get("indicator_code") or ""),
            indicator_label=str(item.get("indicator_label")) if item.get("indicator_label") else None,
            factor_group=str(item.get("factor_group") or "unknown"),
            risk_direction=str(item.get("risk_direction")) if item.get("risk_direction") else None,
            raw_value=float(item["raw_value"]) if item.get("raw_value") is not None else None,
            normalized_risk=float(item["normalized_risk"]) if item.get("normalized_risk") is not None else None,
            contribution_score=float(item["contribution_score"]) if item.get("contribution_score") is not None else None,
            period_date=str(item.get("period_date")) if item.get("period_date") else None,
            source_date=str(item.get("source_date")) if item.get("source_date") else None,
        )
        for item in rows
    ]


def _get_country_result_rows(db: Session, pipeline_run_id: int) -> list[CountryRiskResult]:
    return db.execute(
        select(CountryRiskResult)
        .where(CountryRiskResult.pipeline_run_id == pipeline_run_id)
        .order_by(
            CountryRiskResult.risk_score.desc(),
            CountryRiskResult.confidence_score.desc(),
            CountryRiskResult.country_code.asc(),
        )
    ).scalars().all()


def _build_country_results_response(run: PipelineRun, rows: list[CountryRiskResult]) -> PipelineCountryResultsResponse:
    return PipelineCountryResultsResponse(
        pipeline_run_id=run.id,
        pipeline_name=run.pipeline_name,
        status=run.status,
        finished_at=run.finished_at,
        countries_ranked=len(rows),
        model_version=rows[0].model_version if rows else None,
        countries=[
            CountryRiskRowSchema(
                country_code=row.country_code,
                risk_score=row.risk_score,
                risk_band=row.risk_band,
                disease_burden_score=row.disease_burden_score,
                surveillance_readiness_score=row.surveillance_readiness_score,
                confidence_score=row.confidence_score,
                top_contributors=_serialize_contributors((row.factors_json or {}).get("top_contributors"), limit=3),
            )
            for row in rows
        ],
    )


def _build_country_detail_response(run: PipelineRun, row: CountryRiskResult) -> PipelineCountryDetailResponse:
    factors_json = row.factors_json or {}
    raw_factors = factors_json.get("factors") or {}
    factor_payload = {
        str(name): {
            "score": float(payload.get("score") or 0.0),
            "indicator_count": int(payload["indicator_count"]) if payload.get("indicator_count") is not None else None,
            "expected_indicator_count": int(payload["expected_indicator_count"]) if payload.get("expected_indicator_count") is not None else None,
            "indicator_coverage": float(payload["indicator_coverage"]) if payload.get("indicator_coverage") is not None else None,
            "freshness_score": float(payload["freshness_score"]) if payload.get("freshness_score") is not None else None,
            "uncertainty_quality": float(payload["uncertainty_quality"]) if payload.get("uncertainty_quality") is not None else None,
        }
        for name, payload in raw_factors.items()
    }
    return PipelineCountryDetailResponse(
        pipeline_run_id=run.id,
        pipeline_name=run.pipeline_name,
        status=run.status,
        finished_at=run.finished_at,
        country=CountryRiskDetailSchema(
            country_code=row.country_code,
            risk_score=row.risk_score,
            risk_band=row.risk_band,
            disease_burden_score=row.disease_burden_score,
            surveillance_readiness_score=row.surveillance_readiness_score,
            confidence_score=row.confidence_score,
            factors=factor_payload,
            top_contributors=_serialize_contributors(factors_json.get("top_contributors"), limit=5),
            indicator_details=_serialize_contributors(factors_json.get("indicator_details")),
            model_version=row.model_version,
        ),
    )


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
    try:
        run = _get_pipeline_run_or_404(db, pipeline_run_id)
        stage_rows = db.execute(
            select(PipelineStageRun).where(PipelineStageRun.pipeline_run_id == run.id).order_by(PipelineStageRun.id.asc())
        ).scalars().all()
    except OperationalError as exc:
        if _is_retryable_sqlite_lock(exc):
            logger.warning("pipeline_run_lookup_retry pipeline_run_id=%s error=%s", pipeline_run_id, exc)
            raise HTTPException(status_code=503, detail="database busy; retry") from exc
        raise
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


@router.get("/runs/latest/results", response_model=PipelineCountryResultsResponse)
def get_latest_pipeline_results(db: Session = Depends(get_db_session)) -> PipelineCountryResultsResponse:
    latest_run_id = db.execute(
        select(CountryRiskResult.pipeline_run_id).order_by(desc(CountryRiskResult.pipeline_run_id)).limit(1)
    ).scalar_one_or_none()
    if latest_run_id is None:
        raise HTTPException(status_code=404, detail="no pipeline results found")
    run = _get_pipeline_run_or_404(db, int(latest_run_id))
    rows = _get_country_result_rows(db, run.id)
    return _build_country_results_response(run, rows)


@router.get("/runs/{pipeline_run_id}/results", response_model=PipelineCountryResultsResponse)
def get_pipeline_results(pipeline_run_id: int, db: Session = Depends(get_db_session)) -> PipelineCountryResultsResponse:
    logger.info("pipeline_results_lookup pipeline_run_id=%s", pipeline_run_id)
    run = _get_pipeline_run_or_404(db, pipeline_run_id)
    rows = _get_country_result_rows(db, run.id)
    if not rows:
        raise HTTPException(status_code=404, detail="pipeline results not found")
    return _build_country_results_response(run, rows)


@router.get("/runs/{pipeline_run_id}/results/{country_code}", response_model=PipelineCountryDetailResponse)
def get_pipeline_country_detail(
    pipeline_run_id: int,
    country_code: str,
    db: Session = Depends(get_db_session),
) -> PipelineCountryDetailResponse:
    logger.info("pipeline_country_detail_lookup pipeline_run_id=%s country_code=%s", pipeline_run_id, country_code)
    run = _get_pipeline_run_or_404(db, pipeline_run_id)
    row = db.execute(
        select(CountryRiskResult)
        .where(CountryRiskResult.pipeline_run_id == run.id)
        .where(CountryRiskResult.country_code == country_code.upper())
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="country result not found")
    return _build_country_detail_response(run, row)


@router.get("/runs/{pipeline_run_id}/events", response_model=PipelineEventListResponse)
def get_pipeline_run_events(pipeline_run_id: int, db: Session = Depends(get_db_session)) -> PipelineEventListResponse:
    logger.info("pipeline_events_lookup pipeline_run_id=%s", pipeline_run_id)
    run = _get_pipeline_run_or_404(db, pipeline_run_id)
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

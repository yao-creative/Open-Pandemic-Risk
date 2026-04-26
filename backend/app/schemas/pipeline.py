from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PipelineRunCreateRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, max_length=128)


class PipelineRunCreateResponse(BaseModel):
    pipeline_run_id: int
    status: str
    stage_order: list[str]


class ContributorSchema(BaseModel):
    indicator_code: str
    indicator_label: str | None = None
    factor_group: str
    risk_direction: str | None = None
    raw_value: float | None = None
    normalized_risk: float | None = None
    contribution_score: float | None = None
    period_date: str | None = None
    source_date: str | None = None


class FactorScoreSchema(BaseModel):
    score: float
    indicator_count: int | None = None
    expected_indicator_count: int | None = None
    indicator_coverage: float | None = None
    freshness_score: float | None = None
    uncertainty_quality: float | None = None


class CountryRiskRowSchema(BaseModel):
    country_code: str
    risk_score: float
    risk_band: str
    disease_burden_score: float
    surveillance_readiness_score: float
    confidence_score: float
    top_contributors: list[ContributorSchema]


class CountryRiskDetailSchema(BaseModel):
    country_code: str
    risk_score: float
    risk_band: str
    disease_burden_score: float
    surveillance_readiness_score: float
    confidence_score: float
    factors: dict[str, FactorScoreSchema]
    top_contributors: list[ContributorSchema]
    indicator_details: list[ContributorSchema]
    model_version: str


class PipelineCountryResultsResponse(BaseModel):
    pipeline_run_id: int
    pipeline_name: str
    status: str
    finished_at: datetime | None
    countries_ranked: int
    model_version: str | None
    countries: list[CountryRiskRowSchema]


class PipelineCountryDetailResponse(BaseModel):
    pipeline_run_id: int
    pipeline_name: str
    status: str
    finished_at: datetime | None
    country: CountryRiskDetailSchema


class PipelineStageRunSchema(BaseModel):
    id: int
    stage_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    metrics: dict[str, Any] | None = None
    artifacts: dict[str, Any] | None = None
    error_summary: str | None = None


class PipelineRunStatusResponse(BaseModel):
    pipeline_run_id: int
    pipeline_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    error_summary: str | None
    artifacts: dict[str, Any]
    stage_runs: list[PipelineStageRunSchema]


class PipelineEventSchema(BaseModel):
    id: int
    stage_name: str | None
    event_type: str
    message: str
    payload: dict[str, Any] | None = None
    created_at: datetime


class PipelineEventListResponse(BaseModel):
    pipeline_run_id: int
    events: list[PipelineEventSchema]

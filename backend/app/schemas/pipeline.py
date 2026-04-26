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

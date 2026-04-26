from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SnapshotEnrichRequest(BaseModel):
    snapshot_id: int | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class SnapshotEnrichResponse(BaseModel):
    enrichment_run_id: int
    pipeline_run_id: int
    snapshot_ref_id: int | None
    status: str


class EnrichmentRunStatusResponse(BaseModel):
    enrichment_run_id: int
    pipeline_run_id: int
    snapshot_ref_id: int | None
    status: str
    steps_used: int
    exa_calls_used: int
    max_steps: int
    max_exa_calls: int
    started_at: str | None
    finished_at: str | None
    error_summary: str | None
    report: dict[str, Any] | None = None


class EnrichmentRunListItem(BaseModel):
    enrichment_run_id: int
    pipeline_run_id: int
    snapshot_ref_id: int | None
    status: str
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None


class EnrichmentRunListResponse(BaseModel):
    items: list[EnrichmentRunListItem]
    total: int
    limit: int
    offset: int


class ScoreRunResponse(BaseModel):
    enrichment_run_id: int
    pipeline_run_id: int
    status: str
    risk_value: float
    risk_band: str

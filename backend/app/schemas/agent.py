from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentQueryRequest(BaseModel):
    tool: str = Field(pattern="^(read_run_results|explore_db_readonly|search_exa)$")
    args: dict[str, Any] = Field(default_factory=dict)


class AgentQueryResponse(BaseModel):
    tool: str
    result: dict[str, Any]


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


class ScoreRunResponse(BaseModel):
    enrichment_run_id: int
    pipeline_run_id: int
    status: str
    risk_value: float
    risk_band: str

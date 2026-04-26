from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DebugStageRunRequest(BaseModel):
    snapshot_ref_id: int | None = None
    enrichment_pipeline_run_id: int | None = None
    max_steps: int | None = None
    max_targets: int | None = None
    max_exa_calls: int | None = None
    sample_limit: int | None = None


class DebugStageValidationResponse(BaseModel):
    stage: str
    valid: bool
    errors: list[str]


class DebugStageRunResponse(BaseModel):
    stage: str
    status: str
    metrics: dict[str, Any]
    artifacts: dict[str, Any]
    error: str | None = None


class StageCatalogItem(BaseModel):
    name: str
    required_inputs: list[str]


class StageCatalogResponse(BaseModel):
    stages: list[StageCatalogItem]

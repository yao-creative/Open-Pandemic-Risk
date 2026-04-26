from datetime import datetime

from pydantic import BaseModel


class SourceRunResultSchema(BaseModel):
    source: str
    records_in: int
    records_ok: int
    records_failed: int
    records_skipped: int
    error: str | None = None


class CodeRunResultSchema(BaseModel):
    code: str
    category: str
    status: str
    records_in: int
    records_ok: int
    records_failed: int
    records_skipped: int
    error: str | None = None


class IngestRunResponse(BaseModel):
    pipeline_run_id: int
    status: str
    records_in: int
    records_ok: int
    records_failed: int
    records_skipped: int
    profile_name: str
    codes_total: int
    codes_ok: int
    codes_failed: int
    sources: list[SourceRunResultSchema]
    code_results: list[CodeRunResultSchema]


class PipelineRunDetailResponse(IngestRunResponse):
    pipeline_name: str
    started_at: datetime
    finished_at: datetime | None = None
    error_summary: str | None = None

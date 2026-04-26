from pydantic import BaseModel


class SourceRunResultSchema(BaseModel):
    source: str
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
    sources: list[SourceRunResultSchema]

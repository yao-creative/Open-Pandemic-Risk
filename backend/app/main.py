from dataclasses import asdict

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .azure_client import check_azure_ready
from .db import check_db_ready, get_db_session, init_db
from .models import PipelineRun
from .pipeline.run_ingest import result_from_pipeline_run, run_ingestion
from .schemas import (
    CodeRunResultSchema,
    IngestRunResponse,
    PipelineRunDetailResponse,
    SourceRunResultSchema,
)
from .settings import get_settings

app = FastAPI(title="biohack-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    db_ok, db_error = check_db_ready()
    azure_ok, azure_error = check_azure_ready()

    checks = {
        "db": "ok" if db_ok else "error",
        "azure_openai": "ok" if azure_ok else "error",
    }
    details = [msg for msg in [db_error, azure_error] if msg]

    payload = {
        "ready": db_ok and azure_ok,
        "checks": checks,
        "details": details,
    }

    if payload["ready"]:
        return payload
    return JSONResponse(status_code=503, content=payload)


@app.post("/ingest/run", response_model=IngestRunResponse)
def ingest_run(db: Session = Depends(get_db_session)) -> IngestRunResponse:
    result = run_ingestion(db, get_settings())
    return IngestRunResponse(
        pipeline_run_id=result.pipeline_run_id,
        status=result.status,
        records_in=result.records_in,
        records_ok=result.records_ok,
        records_failed=result.records_failed,
        records_skipped=result.records_skipped,
        profile_name=result.profile_name,
        codes_total=result.codes_total,
        codes_ok=result.codes_ok,
        codes_failed=result.codes_failed,
        sources=[SourceRunResultSchema(**asdict(item)) for item in result.sources],
        code_results=[CodeRunResultSchema(**asdict(item)) for item in result.code_results],
    )


@app.get("/runs/{pipeline_run_id}", response_model=PipelineRunDetailResponse)
def get_run(pipeline_run_id: int, db: Session = Depends(get_db_session)) -> PipelineRunDetailResponse:
    pipeline_run = db.get(PipelineRun, pipeline_run_id)
    if pipeline_run is None:
        raise HTTPException(status_code=404, detail="pipeline run not found")
    result = result_from_pipeline_run(pipeline_run)
    return PipelineRunDetailResponse(
        pipeline_run_id=result.pipeline_run_id,
        pipeline_name=pipeline_run.pipeline_name,
        started_at=pipeline_run.started_at,
        finished_at=pipeline_run.finished_at,
        status=result.status,
        records_in=result.records_in,
        records_ok=result.records_ok,
        records_failed=result.records_failed,
        records_skipped=result.records_skipped,
        error_summary=pipeline_run.error_summary,
        profile_name=result.profile_name,
        codes_total=result.codes_total,
        codes_ok=result.codes_ok,
        codes_failed=result.codes_failed,
        sources=[SourceRunResultSchema(**asdict(item)) for item in result.sources],
        code_results=[CodeRunResultSchema(**asdict(item)) for item in result.code_results],
    )

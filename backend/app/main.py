from dataclasses import asdict

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .azure_client import check_azure_ready
from .db import check_db_ready, get_db_session, init_db
from .pipeline.run_ingest import run_ingestion
from .schemas import IngestRunResponse, SourceRunResultSchema
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
        sources=[SourceRunResultSchema(**asdict(item)) for item in result.sources],
    )

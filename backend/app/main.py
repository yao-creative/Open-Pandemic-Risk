from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import debug_stages_router, pipeline_router
from .azure_client import check_azure_ready
from .db import check_db_ready, init_db, run_startup_preflight_checks

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
    run_startup_preflight_checks()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    db_ok, db_error = check_db_ready()
    azure_ok, azure_error = check_azure_ready()
    payload = {
        "ready": db_ok and azure_ok,
        "checks": {"db": "ok" if db_ok else "error", "azure_openai": "ok" if azure_ok else "error"},
        "details": [msg for msg in [db_error, azure_error] if msg],
    }
    if payload["ready"]:
        return payload
    return JSONResponse(status_code=503, content=payload)


app.include_router(pipeline_router)
app.include_router(debug_stages_router)

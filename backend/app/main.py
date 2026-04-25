from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .azure_client import check_azure_ready
from .db import check_db_ready

app = FastAPI(title="biohack-api")


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

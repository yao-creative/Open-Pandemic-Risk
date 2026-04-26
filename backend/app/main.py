import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import debug_stages_router, pipeline_router
from .azure_client import check_azure_ready
from .db import check_db_ready, init_db
from .logging_utils import configure_logging
from .settings import get_settings

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("biohack.app")

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
    logger.info(
        "startup_complete database_url=%s azure_configured=%s",
        settings.database_url,
        bool(
            settings.azure_openai_endpoint
            and settings.azure_openai_api_key
            and settings.azure_openai_deployment
        ),
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("x-request-id", uuid4().hex[:12])
    started = perf_counter()
    logger.info(
        "request_started request_id=%s method=%s path=%s query=%s client=%s",
        request_id,
        request.method,
        request.url.path,
        request.url.query or "-",
        request.client.host if request.client else "unknown",
    )

    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed request_id=%s path=%s", request_id, request.url.path)
        raise

    duration_ms = round((perf_counter() - started) * 1000, 2)
    response.headers["X-Request-Id"] = request_id
    logger.info(
        "request_completed request_id=%s method=%s path=%s status=%s duration_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


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
        logger.info("readyz_ok checks=%s", payload["checks"])
        return payload
    logger.warning("readyz_failed checks=%s details=%s", payload["checks"], payload["details"])
    return JSONResponse(status_code=503, content=payload)


app.include_router(pipeline_router)
app.include_router(debug_stages_router)

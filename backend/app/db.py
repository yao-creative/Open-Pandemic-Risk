from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .models import Base
from .settings import get_settings


_engine = None
SessionLocal = None


def _resolve_repo_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / path


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        is_sqlite = settings.database_url.startswith("sqlite")
        connect_args = {"check_same_thread": False, "timeout": 60} if is_sqlite else {}
        _engine = create_engine(settings.database_url, connect_args=connect_args)
        if is_sqlite:
            with _engine.begin() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                conn.execute(text("PRAGMA synchronous=NORMAL"))
                conn.execute(text("PRAGMA busy_timeout=60000"))
    return _engine


def get_session_local():
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return SessionLocal


def init_db() -> None:
    Base.metadata.create_all(bind=get_engine())


def _assert_model_artifacts_readable() -> None:
    settings = get_settings()
    required_paths = {
        "ml_model_pickle_path": settings.ml_model_pickle_path,
        "ml_scaler_pickle_path": settings.ml_scaler_pickle_path,
        "ml_model_manifest_path": settings.ml_model_manifest_path,
    }
    for key, raw_path in required_paths.items():
        resolved = _resolve_repo_path(raw_path)
        if not resolved.is_file():
            raise RuntimeError(f"startup preflight failed: missing required model artifact `{key}` at `{resolved}`")
        try:
            with resolved.open("rb"):
                pass
        except OSError as exc:
            raise RuntimeError(
                f"startup preflight failed: unreadable model artifact `{key}` at `{resolved}`: {exc}"
            ) from exc


def _assert_required_schema_columns() -> None:
    required_columns = {
        "pipeline_run": {
            "status",
            "records_in",
            "records_ok",
            "records_failed",
            "records_skipped",
            "error_summary",
            "details_json",
        },
        "pipeline_stage_run": {"stage_name", "status", "error_summary", "artifacts_json"},
        "ml_risk_snapshot": {"snapshot_ref_id", "payload_json", "model_version"},
        "recommendation_response": {"ml_snapshot_id", "response_json", "citations_json"},
    }
    inspector = inspect(get_engine())
    missing_fields: list[str] = []
    for table_name, columns in required_columns.items():
        if not inspector.has_table(table_name):
            missing_fields.append(f"{table_name} (table missing)")
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name in sorted(columns):
            if column_name not in existing_columns:
                missing_fields.append(f"{table_name}.{column_name}")
    if missing_fields:
        details = ", ".join(missing_fields)
        raise RuntimeError(
            "startup preflight failed: database schema is missing required pipeline fields: "
            f"{details}"
        )


def run_startup_preflight_checks() -> None:
    _assert_model_artifacts_readable()
    _assert_required_schema_columns()


def get_db_session() -> Generator[Session, None, None]:
    db = get_session_local()()
    try:
        yield db
    finally:
        db.close()


def check_db_ready() -> tuple[bool, str | None]:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except SQLAlchemyError as exc:
        return False, f"database error: {exc}"

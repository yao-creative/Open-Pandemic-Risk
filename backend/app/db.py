from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .models import Base
from .settings import get_settings


_engine = None
SessionLocal = None


def _is_sqlite_url(database_url: str) -> bool:
    return database_url.startswith("sqlite")


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        connect_args = {}
        if _is_sqlite_url(settings.database_url):
            connect_args = {
                "check_same_thread": False,
                "timeout": settings.sqlite_busy_timeout_seconds,
            }
        _engine = create_engine(settings.database_url, connect_args=connect_args)
        if _is_sqlite_url(settings.database_url):
            busy_timeout_ms = max(int(settings.sqlite_busy_timeout_seconds * 1000), 0)

            @event.listens_for(_engine, "connect")
            def _configure_sqlite(dbapi_connection, _connection_record) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
                if settings.sqlite_enable_wal:
                    cursor.execute("PRAGMA journal_mode = WAL")
                cursor.close()
    return _engine


def get_session_local():
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return SessionLocal


def init_db() -> None:
    Base.metadata.create_all(bind=get_engine())


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

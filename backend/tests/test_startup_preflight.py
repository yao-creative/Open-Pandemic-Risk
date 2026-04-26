from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app import db as db_module
from app import settings as settings_module
from app.main import app


@pytest.fixture(autouse=True)
def _reset_runtime_state() -> None:
    settings_module.get_settings.cache_clear()
    db_module._engine = None
    db_module.SessionLocal = None
    yield
    settings_module.get_settings.cache_clear()
    db_module._engine = None
    db_module.SessionLocal = None


def _write_artifacts(base: Path) -> tuple[Path, Path, Path]:
    model_path = base / "double_lasso_model.pkl"
    scaler_path = base / "double_lasso_scaler.pkl"
    manifest_path = base / "double_lasso_manifest.json"
    model_path.write_bytes(b"model")
    scaler_path.write_bytes(b"scaler")
    manifest_path.write_text("{}", encoding="utf-8")
    return model_path, scaler_path, manifest_path


@pytest.mark.integration_local
def test_startup_fails_when_model_artifact_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "startup-missing-artifact.db"
    _, scaler_path, manifest_path = _write_artifacts(tmp_path)
    missing_model_path = tmp_path / "does-not-exist.pkl"

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ML_MODEL_PICKLE_PATH", str(missing_model_path))
    monkeypatch.setenv("ML_SCALER_PICKLE_PATH", str(scaler_path))
    monkeypatch.setenv("ML_MODEL_MANIFEST_PATH", str(manifest_path))

    with pytest.raises(RuntimeError, match=r"startup preflight failed: missing required model artifact"):
        with TestClient(app):
            pass


@pytest.mark.integration_local
def test_startup_fails_when_db_schema_missing_required_column(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "startup-missing-column.db"
    model_path, scaler_path, manifest_path = _write_artifacts(tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE pipeline_run (
              id INTEGER PRIMARY KEY,
              pipeline_name VARCHAR(64),
              started_at DATETIME,
              finished_at DATETIME,
              status VARCHAR(16),
              records_in INTEGER,
              records_ok INTEGER,
              records_failed INTEGER,
              error_summary VARCHAR(1024),
              details_json JSON
            )
            """
        )
        conn.commit()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ML_MODEL_PICKLE_PATH", str(model_path))
    monkeypatch.setenv("ML_SCALER_PICKLE_PATH", str(scaler_path))
    monkeypatch.setenv("ML_MODEL_MANIFEST_PATH", str(manifest_path))

    with pytest.raises(RuntimeError, match=r"pipeline_run\.records_skipped"):
        with TestClient(app):
            pass

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app import db as db_module
from app import settings as settings_module


@pytest.fixture
def live_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "live_integration.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    settings_module.get_settings.cache_clear()
    db_module._engine = None
    db_module.SessionLocal = None

    from app.main import app

    with TestClient(app) as client:
        yield client

    settings_module.get_settings.cache_clear()
    db_module._engine = None
    db_module.SessionLocal = None


@pytest.mark.integration_live
def test_live_pipeline_run_hits_who(live_client: TestClient):
    resp = live_client.post("/pipeline/run", json={})
    assert resp.status_code == 200

    payload = resp.json()
    assert "pipeline_run_id" in payload
    assert "status" in payload
    assert isinstance(payload["stage_order"], list)

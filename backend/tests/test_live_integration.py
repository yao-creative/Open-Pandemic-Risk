from __future__ import annotations

from pathlib import Path
import os

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
def test_live_ingest_run_hits_promed_and_who(live_client: TestClient):
    if not os.getenv("PROMED_API_KEY"):
        raise AssertionError("PROMED_API_KEY is required for integration_live tests")

    resp = live_client.post("/ingest/run")
    assert resp.status_code == 200

    payload = resp.json()
    assert "pipeline_run_id" in payload
    assert "status" in payload
    assert isinstance(payload["sources"], list)

    by_source = {item["source"]: item for item in payload["sources"]}
    assert "promed" in by_source
    assert "who_odata" in by_source

    # Live integration check is contract-level: source entries should exist,
    # and a successful source should not report an error.
    if by_source["promed"]["error"] is None:
        assert by_source["promed"]["records_in"] >= 0
    if by_source["who_odata"]["error"] is None:
        assert by_source["who_odata"]["records_in"] >= 0

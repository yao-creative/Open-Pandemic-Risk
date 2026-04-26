from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app import db as db_module
from app import settings as settings_module
from app.settings import Settings


@pytest.fixture
def live_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "live-agent-exa.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("AGENT_ALLOWED_TABLES_CSV", "pipeline_run,indicator_snapshot,source_registry")
    settings_module.get_settings.cache_clear()
    db_module._engine = None
    db_module.SessionLocal = None

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

    settings_module.get_settings.cache_clear()
    db_module._engine = None
    db_module.SessionLocal = None


@pytest.mark.integration_live
def test_live_agent_search_exa_uses_env_key(live_client: TestClient):
    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        pytest.skip("EXA_API_KEY is not set in environment")

    settings = Settings()
    assert settings.exa_api_key == api_key

    resp = live_client.post(
        "/agent/query",
        json={"tool": "search_exa", "args": {"query": "avian flu early warning", "num_results": 1}},
    )
    assert resp.status_code == 200
    payload = resp.json()["result"]
    assert payload["count"] >= 1
    assert payload["results"][0]["url"]

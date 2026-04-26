from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app import db as db_module
from app import settings as settings_module
from app.models import AgentToolAudit, IndicatorSnapshot, PipelineRun, SourceRegistry


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "agent-tools.db"
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


@pytest.mark.integration_local
def test_read_run_results_tool(client: TestClient):
    with db_module.get_session_local()() as db:
        run = PipelineRun(
            pipeline_name="phase1_sync_ingestion",
            started_at=datetime.now(tz=UTC),
            finished_at=datetime.now(tz=UTC),
            status="ok",
            records_in=10,
            records_ok=9,
            records_failed=1,
            error_summary=None,
        )
        db.add(run)
        db.commit()
        run_id = run.id

    resp = client.post("/agent/query", json={"tool": "read_run_results", "args": {"run_id": run_id}})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["result"]["id"] == run_id
    assert payload["result"]["status"] == "ok"

    with db_module.get_session_local()() as db:
        audits = db.query(AgentToolAudit).all()
        assert len(audits) == 1
        assert audits[0].tool_name == "read_run_results"
        assert audits[0].success is True


@pytest.mark.integration_local
def test_explore_db_readonly_rejects_non_allowlisted_table(client: TestClient):
    resp = client.post(
        "/agent/query",
        json={"tool": "explore_db_readonly", "args": {"table": "risk_score", "filters": {}, "limit": 10}},
    )
    assert resp.status_code == 400
    assert "not allowed" in resp.json()["detail"]


@pytest.mark.integration_local
def test_explore_db_readonly_honors_row_limit(client: TestClient):
    with db_module.get_session_local()() as db:
        source = SourceRegistry(name="who_odata", kind="api", base_url="https://example.org", poll_interval_minutes=10, enabled=True)
        db.add(source)
        db.flush()
        for idx in range(3):
            db.add(
                IndicatorSnapshot(
                    source_id=source.id,
                    indicator_code=f"WHO_{idx}",
                    country_code="MYS",
                    period_date=datetime(2024, 1, 1, tzinfo=UTC),
                    value=float(idx),
                    unit="u",
                    dim_json={},
                )
            )
        db.commit()

    resp = client.post(
        "/agent/query",
        json={
            "tool": "explore_db_readonly",
            "args": {"table": "indicator_snapshot", "filters": {"country_code": "MYS"}, "limit": 2},
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["result"]["count"] == 2


@pytest.mark.integration_local
def test_search_exa_tool_returns_results(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EXA_API_KEY", "fake-key")
    settings_module.get_settings.cache_clear()

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"url": "https://example.org", "title": "x", "text": "y"}]}

    def fake_post(*args, **kwargs):
        return _FakeResponse()

    monkeypatch.setattr("httpx.post", fake_post)

    resp = client.post(
        "/agent/query",
        json={"tool": "search_exa", "args": {"query": "avian flu", "num_results": 1}},
    )
    assert resp.status_code == 200
    payload = resp.json()["result"]
    assert payload["count"] == 1
    assert payload["results"][0]["url"] == "https://example.org"

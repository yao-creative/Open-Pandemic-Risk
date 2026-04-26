from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app import db as db_module
from app import settings as settings_module
from app.models import EnrichmentRun, IndicatorSnapshot, PipelineRun, SourceRegistry


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "snapshot-enrich.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("EXA_API_KEY", "fake-key")
    settings_module.get_settings.cache_clear()
    db_module._engine = None
    db_module.SessionLocal = None

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

    settings_module.get_settings.cache_clear()
    db_module._engine = None
    db_module.SessionLocal = None


def _install_fake_exa(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"url": "https://example.org/a", "title": "signal", "text": "summary"}]}

    def fake_post(*args, **kwargs):
        return _FakeResponse()

    monkeypatch.setattr("httpx.post", fake_post)


@pytest.mark.integration_local
def test_snapshot_enrich_run_and_score(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _install_fake_exa(monkeypatch)

    with db_module.get_session_local()() as db:
        source = SourceRegistry(name="who_odata", kind="api", base_url="https://example.org", poll_interval_minutes=1440, enabled=True)
        db.add(source)
        db.flush()
        ingest_run = PipelineRun(
            pipeline_name="phase1_sync_ingestion",
            started_at=datetime.now(tz=UTC),
            finished_at=datetime.now(tz=UTC),
            status="ok",
            records_in=2,
            records_ok=2,
            records_failed=0,
            error_summary=None,
        )
        db.add(ingest_run)
        db.flush()
        db.add_all(
            [
                IndicatorSnapshot(
                    source_id=source.id,
                    indicator_code="WHO_1",
                    country_code="MYS",
                    period_date=datetime(2024, 1, 1, tzinfo=UTC),
                    value=10.0,
                    unit="x",
                    dim_json={},
                ),
                IndicatorSnapshot(
                    source_id=source.id,
                    indicator_code="WHO_2",
                    country_code="THA",
                    period_date=datetime(2024, 1, 1, tzinfo=UTC),
                    value=20.0,
                    unit="x",
                    dim_json={},
                ),
            ]
        )
        db.commit()
        snapshot_id = ingest_run.id

    create_resp = client.post(
        "/agent/snapshot-enrich",
        json={"snapshot_id": snapshot_id, "idempotency_key": "run-001"},
    )
    assert create_resp.status_code == 200
    payload = create_resp.json()
    run_id = payload["enrichment_run_id"]
    assert payload["status"] in {"queued", "running", "completed"}

    status_resp = client.get(f"/agent/runs/{run_id}")
    assert status_resp.status_code == 200
    run_payload = status_resp.json()
    assert run_payload["status"] == "completed"
    assert run_payload["report"] is not None
    assert run_payload["report"]["finding_count"] >= 1

    score_resp = client.post(f"/agent/runs/{run_id}/score")
    assert score_resp.status_code == 200
    score_payload = score_resp.json()
    assert score_payload["status"] == "ok"
    assert score_payload["risk_band"] in {"low", "medium", "high", "critical"}


@pytest.mark.integration_local
def test_snapshot_enrich_idempotency_reuses_run(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _install_fake_exa(monkeypatch)

    first = client.post("/agent/snapshot-enrich", json={"idempotency_key": "same-key"})
    assert first.status_code == 200
    second = client.post("/agent/snapshot-enrich", json={"idempotency_key": "same-key"})
    assert second.status_code == 200
    assert first.json()["enrichment_run_id"] == second.json()["enrichment_run_id"]

    with db_module.get_session_local()() as db:
        runs = db.query(EnrichmentRun).filter(EnrichmentRun.idempotency_key == "same-key").all()
        assert len(runs) == 1

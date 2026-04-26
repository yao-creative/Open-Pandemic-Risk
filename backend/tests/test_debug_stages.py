from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app import db as db_module
from app import settings as settings_module
from app.models import IndicatorSnapshot, PipelineRun, SourceRegistry


class _FakeGetResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "value": [
                {
                    "IndicatorCode": "WHOSIS_000001",
                    "SpatialDim": "MYS",
                    "Year": "2024",
                    "NumericValue": 20.0,
                    "DisplayValue": "per 100k",
                }
            ]
        }


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "debug-stages.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
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
def test_debug_stage_catalog_and_validation(client: TestClient):
    catalog = client.get("/debug/stages")
    assert catalog.status_code == 200
    names = [item["name"] for item in catalog.json()["stages"]]
    assert names == ["ingest_snapshot", "enrich_snapshot_agent", "score_snapshot"]

    invalid = client.post("/debug/stages/enrich_snapshot_agent/validate", json={})
    assert invalid.status_code == 200
    payload = invalid.json()
    assert payload["valid"] is False
    assert "snapshot_ref_id" in payload["errors"][0]


@pytest.mark.integration_local
def test_debug_ingest_stage_run(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: _FakeGetResponse())
    result = client.post("/debug/stages/ingest_snapshot/run", json={})
    assert result.status_code == 200
    payload = result.json()
    assert payload["status"] in {"ok", "error"}
    assert "snapshot_ref_id" in payload["artifacts"]


@pytest.mark.integration_local
def test_debug_score_stage_scopes_snapshot_rows(client: TestClient):
    with db_module.get_session_local()() as db:
        source = SourceRegistry(
            name="who_odata",
            kind="api",
            base_url="https://example.org",
            poll_interval_minutes=1440,
            enabled=True,
        )
        db.add(source)
        db.flush()
        db.add_all(
            [
                IndicatorSnapshot(
                    source_id=source.id,
                    indicator_code="A",
                    country_code="MYS",
                    period_date=datetime(2024, 1, 1, tzinfo=UTC),
                    value=90.0,
                    unit="x",
                    dim_json={"_snapshot_ref_id": 111},
                ),
                IndicatorSnapshot(
                    source_id=source.id,
                    indicator_code="B",
                    country_code="THA",
                    period_date=datetime(2024, 1, 1, tzinfo=UTC),
                    value=5.0,
                    unit="x",
                    dim_json={"_snapshot_ref_id": 222},
                ),
            ]
        )
        run = PipelineRun(
            pipeline_name="test-score-target",
            started_at=datetime.now(tz=UTC),
            finished_at=None,
            status="running",
            records_in=0,
            records_ok=0,
            records_failed=0,
            records_skipped=0,
            error_summary=None,
            details_json=None,
        )
        db.add(run)
        db.commit()
        target_pipeline_run_id = run.id

    resp = client.post(
        "/debug/stages/score_snapshot/run",
        json={"snapshot_ref_id": 111, "enrichment_pipeline_run_id": target_pipeline_run_id, "sample_limit": 10},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["metrics"]["records_in"] == 1

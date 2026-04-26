from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app import db as db_module
from app import settings as settings_module
from app.models import CountryRiskResult, PipelineStageRun


class _FakeGetResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakePostResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "results": [
                {"url": "https://example.org/1", "title": "signal 1", "text": "summary 1"},
                {"url": "https://example.org/2", "title": "signal 2", "text": "summary 2"},
            ]
        }


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "pipeline-flow.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("EXA_API_KEY", "fake-exa-key")
    settings_module.get_settings.cache_clear()
    db_module._engine = None
    db_module.SessionLocal = None

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

    settings_module.get_settings.cache_clear()
    db_module._engine = None
    db_module.SessionLocal = None


def _install_fake_external(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, *args, **kwargs):
        code = url.rstrip("/").rsplit("/", 1)[-1]
        readiness_codes = {"SDGIHR2021", "WHS8_110", "MCV2", "WHS4_117", "WHS4_544"}
        if code in readiness_codes:
            payload = {
                "value": [
                    {
                        "IndicatorCode": code,
                        "SpatialDimType": "COUNTRY",
                        "SpatialDim": "MYS",
                        "TimeDim": 2024,
                        "TimeDimensionBegin": "2024-01-01T00:00:00+00:00",
                        "NumericValue": 90.0,
                        "Value": "90",
                    },
                    {
                        "IndicatorCode": code,
                        "SpatialDimType": "COUNTRY",
                        "SpatialDim": "THA",
                        "TimeDim": 2024,
                        "TimeDimensionBegin": "2024-01-01T00:00:00+00:00",
                        "NumericValue": 30.0,
                        "Value": "30",
                    },
                    {
                        "IndicatorCode": code,
                        "SpatialDimType": "COUNTRY",
                        "SpatialDim": "SGP",
                        "TimeDim": 2024,
                        "TimeDimensionBegin": "2024-01-01T00:00:00+00:00",
                        "NumericValue": 95.0,
                        "Value": "95",
                    },
                ]
            }
            return _FakeGetResponse(payload)

        payload = {
            "value": [
                {
                    "IndicatorCode": code,
                    "SpatialDimType": "COUNTRY",
                    "SpatialDim": "MYS",
                    "TimeDim": 2024,
                    "TimeDimensionBegin": "2024-01-01T00:00:00+00:00",
                    "NumericValue": 15.0,
                    "Value": "15",
                    "Low": 12.0,
                    "High": 18.0,
                },
                {
                    "IndicatorCode": code,
                    "SpatialDimType": "COUNTRY",
                    "SpatialDim": "THA",
                    "TimeDim": 2024,
                    "TimeDimensionBegin": "2024-01-01T00:00:00+00:00",
                    "NumericValue": 70.0,
                    "Value": "70",
                    "Low": 60.0,
                    "High": 80.0,
                },
                {
                    "IndicatorCode": code,
                    "SpatialDimType": "COUNTRY",
                    "SpatialDim": "SGP",
                    "TimeDim": 2024,
                    "TimeDimensionBegin": "2024-01-01T00:00:00+00:00",
                    "NumericValue": 5.0,
                    "Value": "5",
                    "Low": 4.0,
                    "High": 6.0,
                },
            ]
        }
        return _FakeGetResponse(payload)

    monkeypatch.setattr("httpx.get", fake_get)
    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: _FakePostResponse())


@pytest.mark.integration_local
def test_pipeline_run_happy_path(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _install_fake_external(monkeypatch)
    create = client.post("/pipeline/run", json={"idempotency_key": "full-run-1"})
    assert create.status_code == 200
    pipeline_run_id = create.json()["pipeline_run_id"]

    status_resp = client.get(f"/pipeline/runs/{pipeline_run_id}")
    assert status_resp.status_code == 200
    payload = status_resp.json()
    assert payload["status"] == "completed"
    assert payload["pipeline_name"] == "pipeline_full_v1"
    stage_names = [item["stage_name"] for item in payload["stage_runs"]]
    assert stage_names == ["ingest_snapshot", "enrich_snapshot_agent", "score_snapshot"]
    assert all(item["status"] == "completed" for item in payload["stage_runs"])
    assert payload["artifacts"]["snapshot_ref_id"] > 0
    assert payload["artifacts"]["enrichment_run_id"] > 0
    assert payload["artifacts"]["countries_ranked"] >= 1
    assert payload["artifacts"]["risk_band"] in {"low", "medium", "high", "critical"}
    assert payload["artifacts"]["top_countries"][0]["country_code"] == "THA"

    events_resp = client.get(f"/pipeline/runs/{pipeline_run_id}/events")
    assert events_resp.status_code == 200
    event_types = [item["event_type"] for item in events_resp.json()["events"]]
    assert "pipeline_started" in event_types
    assert "pipeline_completed" in event_types

    with db_module.get_session_local()() as db:
        stage_rows = db.execute(
            select(PipelineStageRun).where(PipelineStageRun.pipeline_run_id == pipeline_run_id)
        ).scalars().all()
        assert len(stage_rows) == 3
        scores = db.execute(select(CountryRiskResult).order_by(CountryRiskResult.risk_score.desc())).scalars().all()
        assert len(scores) >= 1
        assert scores[0].country_code == "THA"


@pytest.mark.integration_local
def test_pipeline_idempotency_reuses_run(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _install_fake_external(monkeypatch)
    first = client.post("/pipeline/run", json={"idempotency_key": "same-run"})
    second = client.post("/pipeline/run", json={"idempotency_key": "same-run"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["pipeline_run_id"] == second.json()["pipeline_run_id"]

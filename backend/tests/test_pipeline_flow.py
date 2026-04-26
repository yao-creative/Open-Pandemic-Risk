from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app import db as db_module
from app import settings as settings_module
from app.models import MlRiskSnapshot, PipelineStageRun, RecommendationResponse


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
                    "NumericValue": 10.0,
                    "DisplayValue": "per 100k",
                },
                {
                    "IndicatorCode": "WHOSIS_000001",
                    "SpatialDim": "THA",
                    "Year": "2024",
                    "NumericValue": 40.0,
                    "DisplayValue": "per 100k",
                },
            ]
        }


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
    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: _FakeGetResponse())
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
    assert stage_names == ["ingest_snapshot", "enrich_snapshot_agent", "score_snapshot", "recommend_response_agent"]
    assert all(item["status"] == "completed" for item in payload["stage_runs"])
    assert payload["artifacts"]["snapshot_ref_id"] > 0
    assert payload["artifacts"]["enrichment_run_id"] > 0
    assert payload["artifacts"]["ml_snapshot_id"] > 0
    assert payload["artifacts"]["recommendation_response_id"] > 0
    assert payload["artifacts"]["recommendation_level"] in {
        "urgent_response",
        "heightened_monitoring",
        "routine_monitoring",
        "insufficient_evidence",
    }
    assert payload["artifacts"]["confidence"] in {"high", "medium", "low", "unknown"}
    assert payload["artifacts"]["risk_band"] in {"critical", "high", "medium", "low", "unknown"}
    assert isinstance(payload["artifacts"]["risk_value"], float)
    assert isinstance(payload["artifacts"]["citations"], list)
    report = payload["artifacts"]["report"]
    assert isinstance(report, dict)
    assert isinstance(report["risk_analytics"], dict)
    assert isinstance(report["recommendation"], dict)
    assert isinstance(report["evidence"], list)
    assert report["risk_analytics"]["risk_band"] == payload["artifacts"]["risk_band"]
    assert report["recommendation"]["recommendation_level"] == payload["artifacts"]["recommendation_level"]
    assert report["recommendation"]["response_text"] == payload["artifacts"]["response_text"]

    events_resp = client.get(f"/pipeline/runs/{pipeline_run_id}/events")
    assert events_resp.status_code == 200
    event_types = [item["event_type"] for item in events_resp.json()["events"]]
    assert "pipeline_started" in event_types
    assert "pipeline_completed" in event_types

    with db_module.get_session_local()() as db:
        stage_rows = db.execute(
            select(PipelineStageRun).where(PipelineStageRun.pipeline_run_id == pipeline_run_id)
        ).scalars().all()
        assert len(stage_rows) == 4
        responses = db.execute(select(RecommendationResponse).order_by(RecommendationResponse.id.desc())).scalars().all()
        assert len(responses) >= 1
        ml_snapshots = db.execute(select(MlRiskSnapshot).order_by(MlRiskSnapshot.id.desc())).scalars().all()
        assert len(ml_snapshots) >= 1


@pytest.mark.integration_local
def test_pipeline_idempotency_reuses_run(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _install_fake_external(monkeypatch)
    first = client.post("/pipeline/run", json={"idempotency_key": "same-run"})
    second = client.post("/pipeline/run", json={"idempotency_key": "same-run"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["pipeline_run_id"] == second.json()["pipeline_run_id"]

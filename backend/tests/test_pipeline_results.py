from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app import db as db_module
from app import settings as settings_module


class _FakeGetResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "pipeline-results.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    settings_module.get_settings.cache_clear()
    db_module._engine = None
    db_module.SessionLocal = None

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

    settings_module.get_settings.cache_clear()
    db_module._engine = None
    db_module.SessionLocal = None


def _install_fake_who(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, *args, **kwargs):
        code = url.rstrip("/").rsplit("/", 1)[-1]
        readiness_codes = {"SDGIHR2021", "WHS8_110", "MCV2", "WHS4_117", "WHS4_544"}
        if code in readiness_codes:
            return _FakeGetResponse(
                {
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
                            "NumericValue": 25.0,
                            "Value": "25",
                        },
                    ]
                }
            )

        return _FakeGetResponse(
            {
                "value": [
                    {
                        "IndicatorCode": code,
                        "SpatialDimType": "COUNTRY",
                        "SpatialDim": "MYS",
                        "TimeDim": 2024,
                        "TimeDimensionBegin": "2024-01-01T00:00:00+00:00",
                        "NumericValue": 10.0,
                        "Value": "10",
                        "Low": 8.0,
                        "High": 12.0,
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
                ]
            }
        )

    monkeypatch.setattr("httpx.get", fake_get)


@pytest.mark.integration_local
def test_pipeline_results_routes_and_optional_enrichment(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _install_fake_who(monkeypatch)

    create = client.post("/pipeline/run", json={"idempotency_key": "results-run"})
    assert create.status_code == 200
    pipeline_run_id = create.json()["pipeline_run_id"]

    run_status = client.get(f"/pipeline/runs/{pipeline_run_id}")
    assert run_status.status_code == 200
    status_payload = run_status.json()
    assert status_payload["status"] == "completed"
    stage_runs = {item["stage_name"]: item for item in status_payload["stage_runs"]}
    assert stage_runs["enrich_snapshot_agent"]["status"] == "completed"
    assert stage_runs["enrich_snapshot_agent"]["metrics"]["skipped"] is True

    list_resp = client.get(f"/pipeline/runs/{pipeline_run_id}/results")
    assert list_resp.status_code == 200
    list_payload = list_resp.json()
    assert list_payload["countries_ranked"] == 2
    assert [item["country_code"] for item in list_payload["countries"]] == ["THA", "MYS"]
    assert len(list_payload["countries"][0]["top_contributors"]) >= 1

    detail_resp = client.get(f"/pipeline/runs/{pipeline_run_id}/results/THA")
    assert detail_resp.status_code == 200
    detail_payload = detail_resp.json()
    assert detail_payload["country"]["country_code"] == "THA"
    assert detail_payload["country"]["factors"]["confidence"]["score"] > 0
    assert len(detail_payload["country"]["indicator_details"]) >= 1

    latest_resp = client.get("/pipeline/runs/latest/results")
    assert latest_resp.status_code == 200
    assert latest_resp.json()["pipeline_run_id"] == pipeline_run_id

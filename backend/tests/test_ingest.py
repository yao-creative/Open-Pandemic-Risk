from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app import db as db_module
from app.ingest.who_profiles import WhoProfileCode
from app.models import IndicatorSnapshot
from app import settings as settings_module


class _FakeResponse:
    def __init__(self, *, text: str = "", json_data: dict | None = None, status_code: int = 200):
        self.text = text
        self._json_data = json_data or {}
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            req = httpx.Request("GET", "https://example.test")
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError(f"http error: {self.status_code}", request=req, response=resp)

    def json(self) -> dict:
        return self._json_data


WHO_JSON = {
    "value": [
        {
            "IndicatorCode": "WHOSIS_000001",
            "SpatialDim": "MYS",
            "Year": "2024",
            "NumericValue": 12.3,
            "DisplayValue": "per 100k",
        }
    ]
}

WHO_JSON_DUP_CONTENT = {
    "value": [
        {
            "IndicatorCode": "WHOSIS_000001",
            "SpatialDim": "MYS",
            "Year": "2024",
            "NumericValue": 12.3,
            "DisplayValue": "per 100k",
        },
        {
            "IndicatorCode": "WHOSIS_000001",
            "SpatialDim": "MYS",
            "Year": "2024",
            "NumericValue": 12.3,
            "DisplayValue": "per 100k",
        },
    ]
}

WHO_JSON_NUMERIC_ZERO = {
    "value": [
        {
            "IndicatorCode": "WHOSIS_000001",
            "SpatialDim": "MYS",
            "Year": "2024",
            "NumericValue": 0,
            "DisplayValue": "per 100k",
        }
    ]
}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "phase1.db"
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


@pytest.fixture
def single_code_profile(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.pipeline.run_ingest.get_who_surveillance_profile",
        lambda: ("who_surveillance_mvp_v1", [WhoProfileCode("WHOSIS_000001", "event_signals")]),
    )


@pytest.mark.integration_local
def test_ingest_run_success(client: TestClient, monkeypatch: pytest.MonkeyPatch, single_code_profile):
    def fake_get(url: str, timeout: float):
        if "ghoapi" in url:
            return _FakeResponse(json_data=WHO_JSON)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("httpx.get", fake_get)

    resp = client.post("/ingest/run")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["records_in"] == 1
    assert data["records_ok"] == 1
    assert data["records_skipped"] == 0
    assert data["profile_name"] == "who_surveillance_mvp_v1"
    assert data["codes_total"] == 1
    assert data["codes_ok"] == 1
    assert data["codes_failed"] == 0
    assert len(data["code_results"]) == 1
    assert data["code_results"][0]["code"] == "WHOSIS_000001"
    assert len(data["sources"]) == 1
    assert data["sources"][0]["source"] == "who_odata"


@pytest.mark.integration_local
def test_ingest_run_error_when_who_fails(client: TestClient, monkeypatch: pytest.MonkeyPatch, single_code_profile):
    def fake_get(url: str, timeout: float):
        return _FakeResponse(status_code=500)

    monkeypatch.setattr("httpx.get", fake_get)

    resp = client.post("/ingest/run")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert data["records_in"] == 0
    assert data["records_ok"] == 0
    assert data["codes_failed"] == 1
    assert any("http_5xx" in (item["error"] or "") for item in data["code_results"])


@pytest.mark.integration_local
def test_who_numeric_zero_is_preserved(client: TestClient, monkeypatch: pytest.MonkeyPatch, single_code_profile):
    def fake_get(url: str, timeout: float):
        if "ghoapi" in url:
            return _FakeResponse(json_data=WHO_JSON_NUMERIC_ZERO)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("httpx.get", fake_get)

    resp = client.post("/ingest/run")

    assert resp.status_code == 200
    with db_module.SessionLocal() as db:
        value = db.execute(select(IndicatorSnapshot.value)).scalar_one()
    assert value == 0.0


@pytest.mark.integration_local
def test_who_duplicates_are_skipped(client: TestClient, monkeypatch: pytest.MonkeyPatch, single_code_profile):
    def fake_get(url: str, timeout: float):
        if "ghoapi" in url:
            return _FakeResponse(json_data=WHO_JSON_DUP_CONTENT)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("httpx.get", fake_get)

    first = client.post("/ingest/run")
    second = client.post("/ingest/run")

    assert first.status_code == 200 and second.status_code == 200

    first_data = first.json()
    second_data = second.json()

    assert first_data["status"] == "ok"
    assert first_data["records_in"] == 2
    assert first_data["records_ok"] == 1
    assert first_data["records_skipped"] == 1

    assert second_data["status"] == "ok"
    assert second_data["records_in"] == 2
    assert second_data["records_ok"] == 0
    assert second_data["records_skipped"] == 2


@pytest.mark.integration_local
def test_get_run_returns_ingest_diagnostics(client: TestClient, monkeypatch: pytest.MonkeyPatch, single_code_profile):
    def fake_get(url: str, timeout: float):
        if "ghoapi" in url:
            return _FakeResponse(json_data=WHO_JSON)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("httpx.get", fake_get)

    ingest_resp = client.post("/ingest/run")
    assert ingest_resp.status_code == 200
    run_id = ingest_resp.json()["pipeline_run_id"]

    run_resp = client.get(f"/runs/{run_id}")
    assert run_resp.status_code == 200
    payload = run_resp.json()
    assert payload["pipeline_run_id"] == run_id
    assert payload["pipeline_name"] == "who_surveillance_sync_v1"
    assert payload["profile_name"] == "who_surveillance_mvp_v1"
    assert payload["codes_total"] == 1
    assert len(payload["code_results"]) == 1

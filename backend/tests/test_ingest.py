from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app import db as db_module
from app.models import IndicatorSnapshot
from app import settings as settings_module


class _FakeResponse:
    def __init__(self, *, text: str = "", json_data: dict | None = None, status_code: int = 200):
        self.text = text
        self._json_data = json_data or {}
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http error: {self.status_code}")

    def json(self) -> dict:
        return self._json_data


PROMED_RSS = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<rss version="2.0">
  <channel>
    <title>ProMED</title>
    <item>
      <title>Outbreak A</title>
      <link>https://promedmail.org/post/1</link>
      <guid>pm-1</guid>
      <pubDate>Sat, 25 Apr 2026 09:00:00 GMT</pubDate>
      <description>Suspected outbreak details</description>
    </item>
  </channel>
</rss>
"""

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

PROMED_RSS_DUPLICATE_CONTENT_HASH = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>ProMED</title>
    <item>
      <title>Outbreak A</title>
      <link>https://promedmail.org/post/1</link>
      <guid>pm-1</guid>
      <pubDate>Sat, 25 Apr 2026 09:00:00 GMT</pubDate>
      <description>Suspected outbreak details</description>
    </item>
    <item>
      <title>Outbreak A</title>
      <link>https://promedmail.org/post/1</link>
      <guid>pm-2</guid>
      <pubDate>Sat, 25 Apr 2026 10:00:00 GMT</pubDate>
      <description>Suspected outbreak details</description>
    </item>
  </channel>
</rss>
"""


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


def test_ingest_run_success(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    def fake_get(url: str, timeout: float):
        if "promed" in url:
            return _FakeResponse(text=PROMED_RSS)
        if "ghoapi" in url:
            return _FakeResponse(json_data=WHO_JSON)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("httpx.get", fake_get)

    resp = client.post("/ingest/run")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["records_in"] == 2
    assert data["records_ok"] == 2
    assert len(data["sources"]) == 2


def test_ingest_run_partial_failure(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    def fake_get(url: str, timeout: float):
        if "promed" in url:
            return _FakeResponse(status_code=500)
        if "ghoapi" in url:
            return _FakeResponse(json_data=WHO_JSON)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("httpx.get", fake_get)

    resp = client.post("/ingest/run")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert data["records_in"] == 1
    assert data["records_ok"] == 1
    assert any(source["source"] == "promed" and source["error"] for source in data["sources"])


def test_who_numeric_zero_is_preserved(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    def fake_get(url: str, timeout: float):
        if "promed" in url:
            return _FakeResponse(text=PROMED_RSS)
        if "ghoapi" in url:
            return _FakeResponse(json_data=WHO_JSON_NUMERIC_ZERO)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("httpx.get", fake_get)

    resp = client.post("/ingest/run")

    assert resp.status_code == 200
    with db_module.SessionLocal() as db:
        value = db.execute(select(IndicatorSnapshot.value)).scalar_one()
    assert value == 0.0


def test_promed_dedupes_by_content_hash(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    def fake_get(url: str, timeout: float):
        if "promed" in url:
            return _FakeResponse(text=PROMED_RSS_DUPLICATE_CONTENT_HASH)
        if "ghoapi" in url:
            return _FakeResponse(json_data=WHO_JSON)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("httpx.get", fake_get)

    resp = client.post("/ingest/run")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["records_in"] == 3
    assert data["records_ok"] == 2

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app import db as db_module
from app.ingest.errors import SourceIngestError
from app.ingest.promed import ingest_promed_api
from app.models import RawIngestEvent
from app import settings as settings_module


class _FakeResponse:
    def __init__(self, *, json_data: dict | None = None, status_code: int = 200):
        self._json_data = json_data or {}
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            req = httpx.Request("POST", "https://www.promedmail.org/api/v1/alerts")
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError("status error", request=req, response=resp)

    def json(self) -> dict:
        return self._json_data


@pytest.fixture
def db_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "promed_contract.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    settings_module.get_settings.cache_clear()
    db_module._engine = None
    db_module.SessionLocal = None
    db_module.init_db()

    with db_module.get_session_local()() as db:
        yield db

    settings_module.get_settings.cache_clear()
    db_module._engine = None
    db_module.SessionLocal = None


@pytest.mark.contract
def test_promed_contract_parses_alert_list(db_session, monkeypatch: pytest.MonkeyPatch):
    payload = {
        "success": True,
        "data": {
            "alerts": [
                {
                    "alertId": 123,
                    "subject_line": "Alert title",
                    "issueDate": "2026-04-25T12:00:00Z",
                    "url": "https://www.promedmail.org/post/123",
                    "body": "details",
                }
            ],
            "nextCursor": None,
        },
    }

    def fake_post(url: str, headers: dict, json: dict, timeout: float):
        return _FakeResponse(json_data=payload)

    monkeypatch.setattr("httpx.post", fake_post)

    stats = ingest_promed_api(
        db_session,
        api_base_url="https://www.promedmail.org/api/v1",
        api_key="test-key",
        timeout_seconds=5.0,
        item_limit=10,
    )

    assert stats.records_in == 1
    assert stats.records_ok == 1
    assert stats.records_skipped == 0


@pytest.mark.contract
def test_promed_contract_auth_error(db_session, monkeypatch: pytest.MonkeyPatch):
    def fake_post(url: str, headers: dict, json: dict, timeout: float):
        return _FakeResponse(status_code=401)

    monkeypatch.setattr("httpx.post", fake_post)

    with pytest.raises(SourceIngestError) as exc:
        ingest_promed_api(
            db_session,
            api_base_url="https://www.promedmail.org/api/v1",
            api_key="bad-key",
            timeout_seconds=5.0,
            item_limit=10,
        )

    assert exc.value.code == "auth_error"


@pytest.mark.contract
def test_promed_contract_pagination(db_session, monkeypatch: pytest.MonkeyPatch):
    calls = []

    first = {
        "success": True,
        "data": {
            "alerts": [{"alertId": 1, "subject_line": "A", "body": "x"}],
            "nextCursor": "cursor-2",
        },
    }
    second = {
        "success": True,
        "data": {
            "alerts": [{"alertId": 2, "subject_line": "B", "body": "y"}],
            "nextCursor": None,
        },
    }

    def fake_post(url: str, headers: dict, json: dict, timeout: float):
        calls.append(json)
        if json.get("cursor") is None:
            return _FakeResponse(json_data=first)
        return _FakeResponse(json_data=second)

    monkeypatch.setattr("httpx.post", fake_post)

    stats = ingest_promed_api(
        db_session,
        api_base_url="https://www.promedmail.org/api/v1",
        api_key="test-key",
        timeout_seconds=5.0,
        item_limit=2,
    )

    db_session.flush()
    count = db_session.execute(select(func.count(RawIngestEvent.id))).scalar_one()
    assert stats.records_in == 2
    assert stats.records_ok == 2
    assert count == 2
    assert len(calls) == 2


@pytest.mark.contract
def test_promed_contract_duplicates_are_skipped(db_session, monkeypatch: pytest.MonkeyPatch):
    payload = {
        "success": True,
        "data": {
            "alerts": [
                {"alertId": 1, "subject_line": "A", "url": "https://x/1", "body": "same"},
                {"alertId": 2, "subject_line": "A", "url": "https://x/1", "body": "same"},
            ],
            "nextCursor": None,
        },
    }

    def fake_post(url: str, headers: dict, json: dict, timeout: float):
        return _FakeResponse(json_data=payload)

    monkeypatch.setattr("httpx.post", fake_post)

    stats = ingest_promed_api(
        db_session,
        api_base_url="https://www.promedmail.org/api/v1",
        api_key="test-key",
        timeout_seconds=5.0,
        item_limit=10,
    )

    db_session.flush()
    count = db_session.execute(select(func.count(RawIngestEvent.id))).scalar_one()
    assert stats.records_in == 2
    assert stats.records_ok == 1
    assert stats.records_skipped == 1
    assert count == 1

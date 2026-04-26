from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app import db as db_module
from app.ingest.who import ingest_who_odata
from app.models import IndicatorSnapshot
from app import settings as settings_module


class _FakeResponse:
    def __init__(self, *, json_data: dict | None = None, status_code: int = 200):
        self._json_data = json_data or {}
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            req = httpx.Request("GET", "https://ghoapi.azureedge.net/api/WHOSIS_000001")
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError("status error", request=req, response=resp)

    def json(self) -> dict:
        return self._json_data


@pytest.fixture
def db_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "who_contract.db"
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
def test_who_contract_parses_value_list(db_session, monkeypatch: pytest.MonkeyPatch):
    payload = {
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

    def fake_get(url: str, timeout: float):
        return _FakeResponse(json_data=payload)

    monkeypatch.setattr("httpx.get", fake_get)

    stats = ingest_who_odata(
        db_session,
        url="https://ghoapi.azureedge.net/api/WHOSIS_000001",
        timeout_seconds=5.0,
        item_limit=50,
    )

    db_session.flush()
    count = db_session.execute(select(func.count(IndicatorSnapshot.id))).scalar_one()
    assert stats.records_in == 1
    assert stats.records_ok == 1
    assert stats.records_skipped == 0
    assert count == 1

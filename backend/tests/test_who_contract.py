from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app import db as db_module
from app.ingest.who import ingest_who_odata
from app.models import IndicatorSnapshot, PipelineRun, WhoObservation
from app import settings as settings_module
from datetime import UTC, datetime


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
    run = PipelineRun(
        pipeline_name="who-contract-run",
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
    db_session.add(run)
    db_session.flush()
    payload = {
        "value": [
            {
                "IndicatorCode": "WHOSIS_000001",
                "SpatialDim": "MYS",
                "SpatialDimType": "COUNTRY",
                "Year": "2024",
                "NumericValue": 12.3,
                "Value": "12.3 per 100k",
                "Low": 10.0,
                "High": 14.0,
                "Date": "2024-06-01T00:00:00+00:00",
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
        profile_category="disease_burden",
        indicator_label="Test indicator",
        risk_direction="higher_is_worse",
        snapshot_ref_id=run.id,
    )

    db_session.flush()
    count = db_session.execute(select(func.count(IndicatorSnapshot.id))).scalar_one()
    observation = db_session.execute(select(WhoObservation)).scalar_one()
    assert stats.records_in == 1
    assert stats.records_ok == 1
    assert stats.records_skipped == 0
    assert count == 1
    assert observation.pipeline_run_id == run.id
    assert observation.country_code == "MYS"
    assert observation.numeric_value == pytest.approx(12.3)
    assert observation.low_value == pytest.approx(10.0)
    assert observation.high_value == pytest.approx(14.0)
    assert observation.factor_group == "disease_burden"


@pytest.mark.contract
def test_who_contract_keeps_run_scoped_observations_when_snapshot_row_already_exists(db_session, monkeypatch: pytest.MonkeyPatch):
    first_run = PipelineRun(
        pipeline_name="run-one",
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
    second_run = PipelineRun(
        pipeline_name="run-two",
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
    db_session.add_all([first_run, second_run])
    db_session.flush()

    payload = {
        "value": [
            {
                "IndicatorCode": "MDG_0000000020",
                "SpatialDim": "THA",
                "SpatialDimType": "COUNTRY",
                "TimeDim": 2024,
                "TimeDimensionBegin": "2024-01-01T00:00:00+00:00",
                "NumericValue": 40.0,
                "Low": 30.0,
                "High": 60.0,
            }
        ]
    }

    def fake_get(url: str, timeout: float):
        return _FakeResponse(json_data=payload)

    monkeypatch.setattr("httpx.get", fake_get)

    ingest_who_odata(
        db_session,
        url="https://ghoapi.azureedge.net/api/MDG_0000000020",
        timeout_seconds=5.0,
        item_limit=10,
        profile_category="disease_burden",
        indicator_label="TB incidence",
        risk_direction="higher_is_worse",
        snapshot_ref_id=first_run.id,
    )
    ingest_who_odata(
        db_session,
        url="https://ghoapi.azureedge.net/api/MDG_0000000020",
        timeout_seconds=5.0,
        item_limit=10,
        profile_category="disease_burden",
        indicator_label="TB incidence",
        risk_direction="higher_is_worse",
        snapshot_ref_id=second_run.id,
    )

    db_session.flush()
    snapshot_count = db_session.execute(select(func.count(IndicatorSnapshot.id))).scalar_one()
    observation_count = db_session.execute(select(func.count(WhoObservation.id))).scalar_one()
    assert snapshot_count == 1
    assert observation_count == 2

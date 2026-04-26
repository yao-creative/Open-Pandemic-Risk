from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, ExaCitation
from app.pipeline.stages.enrich_with_exa import enrich_with_exa
from app.settings import Settings


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            request = httpx.Request("POST", "https://exa.test/search")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("upstream error", request=request, response=response)

    def json(self) -> dict:
        return self._payload


@pytest.fixture
def db_session(tmp_path: Path) -> Session:
    db_path = tmp_path / "exa-stage.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        yield session


@pytest.mark.unit
def test_exa_stage_persists_citations(monkeypatch: pytest.MonkeyPatch, db_session: Session):
    def fake_post(*args, **kwargs):
        return _FakeResponse(
            payload={
                "results": [
                    {"url": "https://example.org/a", "title": "A", "text": "snippet a"},
                    {"url": "https://example.org/b", "title": "B", "text": "snippet b"},
                ]
            }
        )

    monkeypatch.setattr("httpx.post", fake_post)
    settings = Settings(exa_api_key="test-api-key", exa_num_results=2)

    result = enrich_with_exa(db_session, settings=settings, pipeline_run_id=123, query="avian influenza")
    db_session.commit()

    assert result.status == "ok"
    assert result.citations_saved == 2
    saved = db_session.execute(select(ExaCitation).order_by(ExaCitation.id)).scalars().all()
    assert len(saved) == 2
    assert saved[0].query == "avian influenza"


@pytest.mark.unit
def test_exa_stage_reports_http_error(monkeypatch: pytest.MonkeyPatch, db_session: Session):
    def fake_post(*args, **kwargs):
        return _FakeResponse(status_code=502)

    monkeypatch.setattr("httpx.post", fake_post)
    settings = Settings(exa_api_key="test-api-key", exa_num_results=3)

    result = enrich_with_exa(db_session, settings=settings, pipeline_run_id=123)

    assert result.status == "error"
    assert result.citations_saved == 0
    assert "http_error" in (result.error or "")

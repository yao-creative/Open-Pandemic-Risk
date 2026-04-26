from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
import pytest

from app.models import Base, ExaCitation, PipelineRun
from app.pipeline.stages.enrich_with_exa import enrich_with_exa
from app.settings import Settings


@pytest.fixture
def db_session(tmp_path: Path) -> Session:
    db_path = tmp_path / "live-exa-stage.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        yield session


@pytest.mark.integration_live
def test_live_exa_stage_reads_api_key_from_env(db_session: Session):
    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        pytest.skip("EXA_API_KEY is not set in environment")

    settings = Settings()
    assert settings.exa_api_key == api_key

    run = PipelineRun(
        pipeline_name="phase1_sync_ingestion",
        started_at=datetime.now(tz=UTC),
        finished_at=None,
        status="running",
        records_in=0,
        records_ok=0,
        records_failed=0,
        error_summary=None,
    )
    db_session.add(run)
    db_session.flush()

    result = enrich_with_exa(db_session, settings=settings, pipeline_run_id=run.id, query="avian flu early warning")
    db_session.commit()

    assert result.status == "ok"
    assert result.citations_saved >= 1
    citations = db_session.execute(select(ExaCitation)).scalars().all()
    assert len(citations) >= 1

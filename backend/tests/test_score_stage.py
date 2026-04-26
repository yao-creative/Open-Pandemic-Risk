from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, IndicatorSnapshot, PipelineRun, PipelineRunScore, SourceRegistry
from app.pipeline.stages.score import ScoreFeatures, calculate_risk_value, classify_risk_band, derive_score_features, score_pipeline_run


@pytest.fixture
def db_session(tmp_path: Path) -> Session:
    db_path = tmp_path / "score-stage.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        yield session


@pytest.mark.unit
def test_scoring_transforms_are_deterministic():
    features = derive_score_features([5.0, 15.0, 25.0])
    assert features == ScoreFeatures(signal_count=3, mean_value=15.0, max_value=25.0)
    risk = calculate_risk_value(features)
    assert risk == pytest.approx(0.305)
    assert classify_risk_band(risk) == "medium"


@pytest.mark.unit
def test_score_stage_persists_pipeline_run_score(db_session: Session):
    source = SourceRegistry(name="who_odata", kind="api", base_url="https://example.org", poll_interval_minutes=1440, enabled=True)
    db_session.add(source)
    db_session.flush()
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
    db_session.add_all(
        [
            IndicatorSnapshot(
                source_id=source.id,
                indicator_code="WHO_1",
                country_code="MYS",
                period_date=datetime(2024, 1, 1, tzinfo=UTC),
                value=10.0,
                unit="x",
                dim_json={},
            ),
            IndicatorSnapshot(
                source_id=source.id,
                indicator_code="WHO_2",
                country_code="MYS",
                period_date=datetime(2024, 1, 1, tzinfo=UTC),
                value=90.0,
                unit="x",
                dim_json={},
            ),
        ]
    )

    result = score_pipeline_run(db_session, pipeline_run_id=run.id)
    db_session.commit()

    assert result.status == "ok"
    assert result.records_in == 2
    assert result.records_ok == 1
    score_row = db_session.execute(select(PipelineRunScore)).scalar_one()
    assert score_row.pipeline_run_id == run.id
    assert score_row.risk_band in {"medium", "high", "critical"}

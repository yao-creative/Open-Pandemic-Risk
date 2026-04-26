from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, CountryRiskResult, PipelineRun, SourceRegistry, WhoObservation
from app.pipeline.stages.score import classify_risk_band, score_pipeline_run


@pytest.fixture
def db_session(tmp_path: Path) -> Session:
    db_path = tmp_path / "score-stage.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        yield session


@pytest.mark.unit
def test_risk_band_thresholds_are_stable():
    assert classify_risk_band(0.8) == "critical"
    assert classify_risk_band(0.6) == "high"
    assert classify_risk_band(0.3) == "medium"
    assert classify_risk_band(0.1) == "low"


@pytest.mark.integration_local
def test_score_stage_persists_country_risk_results(db_session: Session):
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
            WhoObservation(
                pipeline_run_id=run.id,
                source_id=source.id,
                indicator_code="MDG_0000000020",
                indicator_label="TB incidence",
                factor_group="disease_burden",
                risk_direction="higher_is_worse",
                country_code="MYS",
                spatial_dim_type="COUNTRY",
                period_date=datetime(2024, 1, 1, tzinfo=UTC),
                source_date=datetime(2024, 6, 1, tzinfo=UTC),
                numeric_value=10.0,
                low_value=8.0,
                high_value=12.0,
                display_value="10",
                dimension_key="",
                dimension_json={},
            ),
            WhoObservation(
                pipeline_run_id=run.id,
                source_id=source.id,
                indicator_code="SDGIHR2021",
                indicator_label="SPAR score",
                factor_group="surveillance_readiness",
                risk_direction="higher_is_better",
                country_code="MYS",
                spatial_dim_type="COUNTRY",
                period_date=datetime(2024, 1, 1, tzinfo=UTC),
                source_date=datetime(2024, 6, 1, tzinfo=UTC),
                numeric_value=90.0,
                low_value=None,
                high_value=None,
                display_value="90",
                dimension_key="",
                dimension_json={},
            ),
            WhoObservation(
                pipeline_run_id=run.id,
                source_id=source.id,
                indicator_code="MDG_0000000020",
                indicator_label="TB incidence",
                factor_group="disease_burden",
                risk_direction="higher_is_worse",
                country_code="THA",
                spatial_dim_type="COUNTRY",
                period_date=datetime(2024, 1, 1, tzinfo=UTC),
                source_date=datetime(2024, 6, 1, tzinfo=UTC),
                numeric_value=80.0,
                low_value=60.0,
                high_value=100.0,
                display_value="80",
                dimension_key="",
                dimension_json={},
            ),
            WhoObservation(
                pipeline_run_id=run.id,
                source_id=source.id,
                indicator_code="SDGIHR2021",
                indicator_label="SPAR score",
                factor_group="surveillance_readiness",
                risk_direction="higher_is_better",
                country_code="THA",
                spatial_dim_type="COUNTRY",
                period_date=datetime(2024, 1, 1, tzinfo=UTC),
                source_date=datetime(2024, 6, 1, tzinfo=UTC),
                numeric_value=30.0,
                low_value=None,
                high_value=None,
                display_value="30",
                dimension_key="",
                dimension_json={},
            ),
        ]
    )

    result = score_pipeline_run(db_session, pipeline_run_id=run.id)
    db_session.commit()

    assert result.status == "ok"
    assert result.records_in == 4
    assert result.records_ok == 2
    rows = db_session.execute(select(CountryRiskResult).order_by(CountryRiskResult.risk_score.desc())).scalars().all()
    assert [row.country_code for row in rows] == ["THA", "MYS"]
    assert rows[0].risk_band in {"medium", "high", "critical"}
    assert rows[0].factors_json["factors"]["confidence"]["score"] > 0


@pytest.mark.integration_local
def test_score_stage_damps_risk_when_confidence_is_weaker(db_session: Session):
    source = SourceRegistry(name="who_odata", kind="api", base_url="https://example.org", poll_interval_minutes=1440, enabled=True)
    db_session.add(source)
    db_session.flush()
    run = PipelineRun(
        pipeline_name="confidence-check",
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
    db_session.add_all(
        [
            WhoObservation(
                pipeline_run_id=run.id,
                source_id=source.id,
                indicator_code="MDG_0000000020",
                indicator_label="TB incidence",
                factor_group="disease_burden",
                risk_direction="higher_is_worse",
                country_code="AAA",
                spatial_dim_type="COUNTRY",
                period_date=datetime(2024, 1, 1, tzinfo=UTC),
                source_date=datetime(2024, 6, 1, tzinfo=UTC),
                numeric_value=90.0,
                low_value=80.0,
                high_value=100.0,
                display_value="90",
                dimension_key="",
                dimension_json={},
            ),
            WhoObservation(
                pipeline_run_id=run.id,
                source_id=source.id,
                indicator_code="SDGIHR2021",
                indicator_label="SPAR score",
                factor_group="surveillance_readiness",
                risk_direction="higher_is_better",
                country_code="AAA",
                spatial_dim_type="COUNTRY",
                period_date=datetime(2024, 1, 1, tzinfo=UTC),
                source_date=datetime(2024, 6, 1, tzinfo=UTC),
                numeric_value=20.0,
                low_value=None,
                high_value=None,
                display_value="20",
                dimension_key="",
                dimension_json={},
            ),
            WhoObservation(
                pipeline_run_id=run.id,
                source_id=source.id,
                indicator_code="MDG_0000000020",
                indicator_label="TB incidence",
                factor_group="disease_burden",
                risk_direction="higher_is_worse",
                country_code="BBB",
                spatial_dim_type="COUNTRY",
                period_date=datetime(2010, 1, 1, tzinfo=UTC),
                source_date=datetime(2010, 6, 1, tzinfo=UTC),
                numeric_value=90.0,
                low_value=10.0,
                high_value=170.0,
                display_value="90",
                dimension_key="",
                dimension_json={},
            ),
        ]
    )

    score_pipeline_run(db_session, pipeline_run_id=run.id)
    db_session.commit()

    rows = db_session.execute(select(CountryRiskResult).order_by(CountryRiskResult.risk_score.desc())).scalars().all()
    assert [row.country_code for row in rows] == ["AAA", "BBB"]
    assert rows[0].confidence_score > rows[1].confidence_score

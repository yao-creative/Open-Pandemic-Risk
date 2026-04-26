from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SourceRegistry(Base):
    __tablename__ = "source_registry"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    poll_interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class RawIngestEvent(Base):
    __tablename__ = "raw_ingest_event"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_raw_source_external"),
        UniqueConstraint("source_id", "content_hash", name="uq_raw_source_content_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source_registry.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(512))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)


class CanonicalEvent(Base):
    __tablename__ = "canonical_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    pathogen_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    location_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="suspected")


class EventObservation(Base):
    __tablename__ = "event_observation"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_event_id: Mapped[int] = mapped_column(ForeignKey("canonical_event.id"), index=True)
    raw_ingest_event_id: Mapped[int] = mapped_column(ForeignKey("raw_ingest_event.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    case_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    death_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transmission_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    novelty_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    extract_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    verification_state: Mapped[str | None] = mapped_column(String(32), nullable=True)


class IndicatorSnapshot(Base):
    __tablename__ = "indicator_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "indicator_code",
            "country_code",
            "period_date",
            name="uq_indicator_snapshot",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source_registry.id"), index=True)
    indicator_code: Mapped[str] = mapped_column(String(64), index=True)
    country_code: Mapped[str] = mapped_column(String(16), index=True)
    period_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dim_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class WhoObservation(Base):
    __tablename__ = "who_observation"
    __table_args__ = (
        UniqueConstraint(
            "pipeline_run_id",
            "indicator_code",
            "country_code",
            "period_date",
            "dimension_key",
            name="uq_who_observation_run_indicator_country_period_dim",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_run.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source_registry.id"), index=True)
    indicator_code: Mapped[str] = mapped_column(String(64), index=True)
    indicator_label: Mapped[str] = mapped_column(String(256))
    factor_group: Mapped[str] = mapped_column(String(64), index=True)
    risk_direction: Mapped[str] = mapped_column(String(32))
    country_code: Mapped[str] = mapped_column(String(16), index=True)
    spatial_dim_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    period_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    source_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    numeric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    display_value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    dimension_key: Mapped[str] = mapped_column(String(256), default="", index=True)
    dimension_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class RiskScore(Base):
    __tablename__ = "risk_score"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_event_id: Mapped[int] = mapped_column(ForeignKey("canonical_event.id"), index=True)
    country_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    risk_value: Mapped[float] = mapped_column(Float)
    risk_band: Mapped[str] = mapped_column(String(16))
    score_factors_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Alert(Base):
    __tablename__ = "alert"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_event_id: Mapped[int] = mapped_column(ForeignKey("canonical_event.id"), index=True)
    risk_score_id: Mapped[int | None] = mapped_column(ForeignKey("risk_score.id"), nullable=True)
    alert_level: Mapped[str] = mapped_column(String(16))
    trigger_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PipelineRun(Base):
    __tablename__ = "pipeline_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_name: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    records_in: Mapped[int] = mapped_column(Integer, default=0)
    records_ok: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PipelineStageRun(Base):
    __tablename__ = "pipeline_stage_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_run.id"), index=True)
    stage_name: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    artifacts_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class PipelineRunEvent(Base):
    __tablename__ = "pipeline_run_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_run.id"), index=True)
    stage_name: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(String(1024))
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentToolAudit(Base):
    __tablename__ = "agent_tool_audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_name: Mapped[str] = mapped_column(String(64), index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean)
    args_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class ExaCitation(Base):
    __tablename__ = "exa_citation"

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_run.id"), index=True)
    url: Mapped[str] = mapped_column(String(1024))
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    snippet: Mapped[str | None] = mapped_column(String, nullable=True)
    query: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PipelineRunScore(Base):
    __tablename__ = "pipeline_run_score"

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_run.id"), index=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    risk_value: Mapped[float] = mapped_column(Float)
    risk_band: Mapped[str] = mapped_column(String(16))
    factors_json: Mapped[dict] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(String(32), default="deterministic-v1")


class CountryRiskResult(Base):
    __tablename__ = "country_risk_result"
    __table_args__ = (
        UniqueConstraint("pipeline_run_id", "country_code", name="uq_country_risk_result_run_country"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_run.id"), index=True)
    country_code: Mapped[str] = mapped_column(String(16), index=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    risk_score: Mapped[float] = mapped_column(Float)
    risk_band: Mapped[str] = mapped_column(String(16), index=True)
    disease_burden_score: Mapped[float] = mapped_column(Float)
    surveillance_readiness_score: Mapped[float] = mapped_column(Float)
    confidence_score: Mapped[float] = mapped_column(Float)
    factors_json: Mapped[dict] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(String(32), default="country-risk-v1")


class EnrichmentRun(Base):
    __tablename__ = "enrichment_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_run.id"), index=True)
    snapshot_ref_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_run.id"), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    max_steps: Mapped[int] = mapped_column(Integer, default=10)
    max_targets: Mapped[int] = mapped_column(Integer, default=5)
    max_exa_calls: Mapped[int] = mapped_column(Integer, default=5)
    steps_used: Mapped[int] = mapped_column(Integer, default=0)
    exa_calls_used: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class ContextDump(Base):
    __tablename__ = "context_dump"
    __table_args__ = (UniqueConstraint("enrichment_run_id", name="uq_context_dump_run"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    enrichment_run_id: Mapped[int] = mapped_column(ForeignKey("enrichment_run.id"), index=True)
    context_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EnrichmentFinding(Base):
    __tablename__ = "enrichment_finding"

    id: Mapped[int] = mapped_column(primary_key=True)
    enrichment_run_id: Mapped[int] = mapped_column(ForeignKey("enrichment_run.id"), index=True)
    target_key: Mapped[str] = mapped_column(String(128), index=True)
    query: Mapped[str] = mapped_column(String(512))
    finding_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EnrichmentReport(Base):
    __tablename__ = "enrichment_report"
    __table_args__ = (UniqueConstraint("enrichment_run_id", name="uq_enrichment_report_run"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    enrichment_run_id: Mapped[int] = mapped_column(ForeignKey("enrichment_run.id"), index=True)
    summary_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

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

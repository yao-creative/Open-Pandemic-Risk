from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IndicatorSnapshot, SourceRegistry


@dataclass
class IngestStats:
    records_in: int = 0
    records_ok: int = 0
    records_failed: int = 0
    records_skipped: int = 0


def _parse_period_date(entry: dict) -> datetime | None:
    value = entry.get("Year") or entry.get("TimeDimensionValue") or entry.get("Dim1")
    if value is None:
        return None
    try:
        year = int(str(value)[:4])
        return datetime(year, 1, 1, tzinfo=UTC)
    except Exception:
        return None


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _get_or_create_source(db: Session, name: str, kind: str, base_url: str, poll_interval_minutes: int) -> SourceRegistry:
    source = db.execute(select(SourceRegistry).where(SourceRegistry.name == name)).scalar_one_or_none()
    if source:
        return source
    source = SourceRegistry(
        name=name,
        kind=kind,
        base_url=base_url,
        poll_interval_minutes=poll_interval_minutes,
        enabled=True,
    )
    db.add(source)
    db.flush()
    return source


def ingest_who_odata(
    db: Session,
    url: str,
    timeout_seconds: float,
    item_limit: int,
    *,
    profile_name: str | None = None,
    profile_category: str | None = None,
    snapshot_ref_id: int | None = None,
) -> IngestStats:
    stats = IngestStats()
    seen_keys: set[tuple[str, str, datetime | None]] = set()
    source = _get_or_create_source(
        db,
        name="who_odata",
        kind="api",
        base_url=url,
        poll_interval_minutes=24 * 60,
    )

    response = httpx.get(url, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    values = payload.get("value", [])
    indicator_code_hint = url.rstrip("/").rsplit("/", 1)[-1]

    for entry in values[:item_limit]:
        stats.records_in += 1
        indicator_code = str(entry.get("IndicatorCode") or entry.get("Indicator") or indicator_code_hint or "unknown")
        country_code = str(
            entry.get("SpatialDim")
            or entry.get("Country")
            or entry.get("CountryCode")
            or "UNK"
        )
        period_date = _parse_period_date(entry)
        dedupe_key = (indicator_code, country_code, period_date)
        if dedupe_key in seen_keys:
            stats.records_skipped += 1
            continue
        numeric_raw = entry.get("NumericValue")
        if numeric_raw is None:
            numeric_raw = entry.get("Value")
        numeric_value = _to_float(numeric_raw)
        unit = entry.get("DisplayValue")
        if unit is not None:
            unit = str(unit)

        existing = db.execute(
            select(IndicatorSnapshot).where(
                IndicatorSnapshot.source_id == source.id,
                IndicatorSnapshot.indicator_code == indicator_code,
                IndicatorSnapshot.country_code == country_code,
                IndicatorSnapshot.period_date == period_date,
            )
        ).scalar_one_or_none()
        if existing:
            stats.records_skipped += 1
            continue

        tagged_entry = dict(entry)
        if profile_name is not None:
            tagged_entry["_profile_name"] = profile_name
        if profile_category is not None:
            tagged_entry["_profile_category"] = profile_category
        if snapshot_ref_id is not None:
            tagged_entry["_snapshot_ref_id"] = snapshot_ref_id

        record = IndicatorSnapshot(
            source_id=source.id,
            indicator_code=indicator_code,
            country_code=country_code,
            period_date=period_date,
            value=numeric_value,
            unit=unit,
            dim_json=tagged_entry,
        )
        db.add(record)
        seen_keys.add(dedupe_key)
        stats.records_ok += 1

    return stats

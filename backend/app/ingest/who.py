from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IndicatorSnapshot, SourceRegistry, WhoObservation


@dataclass
class IngestStats:
    records_in: int = 0
    records_ok: int = 0
    records_failed: int = 0
    records_skipped: int = 0


def _parse_period_date(entry: dict) -> datetime | None:
    begin_value = entry.get("TimeDimensionBegin")
    if begin_value:
        return _parse_datetime(begin_value)

    for value in (entry.get("Year"), entry.get("TimeDim"), entry.get("TimeDimensionValue")):
        if value is None:
            continue
        try:
            year = int(str(value)[:4])
            return datetime(year, 1, 1, tzinfo=UTC)
        except Exception:
            continue
    return None


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _dimension_payload(entry: dict) -> tuple[str, dict[str, object]]:
    payload = {
        "parent_location_code": entry.get("ParentLocationCode"),
        "parent_location": entry.get("ParentLocation"),
        "dim1_type": entry.get("Dim1Type"),
        "dim1": entry.get("Dim1"),
        "dim2_type": entry.get("Dim2Type"),
        "dim2": entry.get("Dim2"),
        "dim3_type": entry.get("Dim3Type"),
        "dim3": entry.get("Dim3"),
        "data_source_dim_type": entry.get("DataSourceDimType"),
        "data_source_dim": entry.get("DataSourceDim"),
        "time_dim_type": entry.get("TimeDimType"),
        "time_dim": entry.get("TimeDim"),
        "time_dimension_value": entry.get("TimeDimensionValue"),
    }
    compact = {key: value for key, value in payload.items() if value not in (None, "")}
    return json.dumps(compact, sort_keys=True, separators=(",", ":")), compact


def _is_country_row(entry: dict, country_code: str) -> bool:
    spatial_dim_type = entry.get("SpatialDimType")
    if country_code in {"", "UNK"}:
        return False
    if spatial_dim_type is None:
        return True
    return str(spatial_dim_type).upper() == "COUNTRY"


def _display_value(entry: dict) -> str | None:
    value = entry.get("Value")
    if value not in (None, ""):
        return str(value)
    display = entry.get("DisplayValue")
    if display not in (None, ""):
        return str(display)
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
    indicator_label: str | None = None,
    risk_direction: str | None = None,
    snapshot_ref_id: int | None = None,
) -> IngestStats:
    stats = IngestStats()
    seen_keys: set[tuple[str, str, datetime | None]] = set()
    response = httpx.get(url, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    source = _get_or_create_source(
        db,
        name="who_odata",
        kind="api",
        base_url=url,
        poll_interval_minutes=24 * 60,
    )
    values = payload.get("value", [])
    indicator_code_hint = url.rstrip("/").rsplit("/", 1)[-1]

    for entry in values[:item_limit]:
        stats.records_in += 1
        indicator_code = str(indicator_code_hint or entry.get("IndicatorCode") or entry.get("Indicator") or "unknown")
        country_code = str(
            entry.get("SpatialDim")
            or entry.get("Country")
            or entry.get("CountryCode")
            or "UNK"
        )
        period_date = _parse_period_date(entry)
        dimension_key, dimension_payload = _dimension_payload(entry)
        dedupe_key = (indicator_code, country_code, period_date, dimension_key)
        if dedupe_key in seen_keys:
            stats.records_skipped += 1
            continue
        if not _is_country_row(entry, country_code):
            stats.records_skipped += 1
            continue
        numeric_raw = entry.get("NumericValue")
        if numeric_raw is None:
            numeric_raw = entry.get("Value")
        numeric_value = _to_float(numeric_raw)
        unit = entry.get("DisplayValue")
        if unit is not None:
            unit = str(unit)
        low_value = _to_float(entry.get("Low"))
        high_value = _to_float(entry.get("High"))
        display_value = _display_value(entry)
        source_date = _parse_datetime(entry.get("Date"))

        existing = db.execute(
            select(IndicatorSnapshot).where(
                IndicatorSnapshot.source_id == source.id,
                IndicatorSnapshot.indicator_code == indicator_code,
                IndicatorSnapshot.country_code == country_code,
                IndicatorSnapshot.period_date == period_date,
            )
        ).scalar_one_or_none()

        tagged_entry = dict(entry)
        if profile_name is not None:
            tagged_entry["_profile_name"] = profile_name
        if profile_category is not None:
            tagged_entry["_profile_category"] = profile_category
        if snapshot_ref_id is not None:
            tagged_entry["_snapshot_ref_id"] = snapshot_ref_id

        if existing is None:
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
            db.flush()

        if snapshot_ref_id is not None:
            observation = WhoObservation(
                pipeline_run_id=snapshot_ref_id,
                source_id=source.id,
                indicator_code=indicator_code,
                indicator_label=indicator_label or indicator_code,
                factor_group=profile_category or "unknown",
                risk_direction=risk_direction or "higher_is_worse",
                country_code=country_code,
                spatial_dim_type=str(entry.get("SpatialDimType")) if entry.get("SpatialDimType") is not None else None,
                period_date=period_date,
                source_date=source_date,
                numeric_value=numeric_value,
                low_value=low_value,
                high_value=high_value,
                display_value=display_value,
                dimension_key=dimension_key,
                dimension_json=dimension_payload,
            )
            db.add(observation)

        seen_keys.add(dedupe_key)
        stats.records_ok += 1

    return stats

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ingest.errors import SourceIngestError
from app.models import RawIngestEvent, SourceRegistry


@dataclass
class IngestStats:
    records_in: int = 0
    records_ok: int = 0
    records_failed: int = 0
    records_skipped: int = 0


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text.replace("Z", "+00:00"))

    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except ValueError:
            continue
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


def _extract_alerts_and_cursor(payload: object) -> tuple[list[dict], str | None]:
    if not isinstance(payload, dict):
        raise SourceIngestError("parse_error", "unexpected ProMED payload shape")

    data = payload.get("data")
    if isinstance(data, list):
        alerts = data
        cursor = payload.get("cursor") or payload.get("nextCursor")
        return alerts, cursor if isinstance(cursor, str) else None

    if isinstance(data, dict):
        alerts_obj = data.get("alerts")
        if isinstance(alerts_obj, list):
            cursor = data.get("cursor") or data.get("nextCursor")
            return alerts_obj, cursor if isinstance(cursor, str) else None

        items_obj = data.get("items")
        if isinstance(items_obj, list):
            cursor = data.get("cursor") or data.get("nextCursor")
            return items_obj, cursor if isinstance(cursor, str) else None

        results_obj = data.get("results")
        if isinstance(results_obj, list):
            cursor = data.get("cursor") or data.get("nextCursor")
            return results_obj, cursor if isinstance(cursor, str) else None

    alerts = payload.get("alerts")
    if isinstance(alerts, list):
        cursor = payload.get("cursor") or payload.get("nextCursor")
        return alerts, cursor if isinstance(cursor, str) else None

    raise SourceIngestError("parse_error", "no alerts list found in ProMED payload")


def _field(alert: dict, *names: str) -> object:
    for name in names:
        if name in alert and alert[name] is not None:
            return alert[name]
    return None


def ingest_promed_api(
    db: Session,
    api_base_url: str,
    api_key: str | None,
    timeout_seconds: float,
    item_limit: int,
) -> IngestStats:
    if not api_key:
        raise SourceIngestError("auth_error", "missing PROMED_API_KEY")

    now = datetime.now(tz=UTC)
    stats = IngestStats()
    seen_external_ids: set[str] = set()
    seen_content_hashes: set[str] = set()

    source = _get_or_create_source(
        db,
        name="promed",
        kind="api",
        base_url=api_base_url,
        poll_interval_minutes=10,
    )

    url = f"{api_base_url.rstrip('/')}/alerts"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    remaining = item_limit
    cursor: str | None = None

    while remaining > 0:
        payload = {"limit": min(remaining, 100), "cursor": cursor}
        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=timeout_seconds)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code in (401, 403):
                raise SourceIngestError("auth_error", f"ProMED auth failed with status {status_code}") from exc
            raise SourceIngestError("http_4xx" if status_code and 400 <= status_code < 500 else "http_5xx", str(exc)) from exc
        except httpx.TimeoutException as exc:
            raise SourceIngestError("timeout_error", str(exc)) from exc
        except httpx.HTTPError as exc:
            raise SourceIngestError("network_error", str(exc)) from exc

        try:
            response_payload = response.json()
        except json.JSONDecodeError as exc:
            raise SourceIngestError("parse_error", f"invalid ProMED JSON: {exc}") from exc

        alerts, next_cursor = _extract_alerts_and_cursor(response_payload)
        if not alerts:
            break

        for alert in alerts:
            stats.records_in += 1

            alert_id = _field(alert, "alertId", "id", "_id", "postId")
            title = _field(alert, "post_title", "subject_line", "title")
            url_value = _field(alert, "url", "link")
            content = _field(alert, "post", "body", "description", "content")
            issue_date = _field(alert, "issueDate", "publishedAt", "published_at", "date")

            title_text = str(title).strip() if title is not None else ""
            content_text = str(content).strip() if content is not None else ""
            url_text = str(url_value).strip() if url_value is not None else ""
            external_id = str(alert_id).strip() if alert_id is not None else ""
            if not external_id:
                external_id = hashlib.sha256(f"{title_text}\n{url_text}\n{content_text}".encode("utf-8")).hexdigest()

            published_at = _parse_datetime(issue_date)
            raw_json = alert
            content_hash = hashlib.sha256(f"{title_text}\n{content_text}\n{url_text}".encode("utf-8")).hexdigest()

            if external_id in seen_external_ids or content_hash in seen_content_hashes:
                stats.records_skipped += 1
                continue

            existing = db.execute(
                select(RawIngestEvent).where(
                    RawIngestEvent.source_id == source.id,
                    or_(
                        RawIngestEvent.external_id == external_id,
                        RawIngestEvent.content_hash == content_hash,
                    ),
                )
            ).scalar_one_or_none()

            if existing:
                stats.records_skipped += 1
                continue

            record = RawIngestEvent(
                source_id=source.id,
                external_id=external_id,
                fetched_at=now,
                published_at=published_at,
                url=url_text or None,
                title=title_text or None,
                raw_text=content_text or None,
                raw_json=raw_json,
                content_hash=content_hash,
            )
            db.add(record)
            seen_external_ids.add(external_id)
            seen_content_hashes.add(content_hash)
            stats.records_ok += 1
            remaining -= 1

            if remaining <= 0:
                break

        if remaining <= 0 or not next_cursor:
            break

        cursor = next_cursor

    return stats

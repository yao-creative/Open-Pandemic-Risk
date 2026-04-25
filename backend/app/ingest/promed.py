from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RawIngestEvent, SourceRegistry


@dataclass
class IngestStats:
    records_in: int = 0
    records_ok: int = 0
    records_failed: int = 0


def _parse_rss_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
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


def ingest_promed_rss(db: Session, rss_url: str, timeout_seconds: float, item_limit: int) -> IngestStats:
    now = datetime.now(tz=UTC)
    stats = IngestStats()

    source = _get_or_create_source(
        db,
        name="promed",
        kind="rss",
        base_url=rss_url,
        poll_interval_minutes=10,
    )

    response = httpx.get(rss_url, timeout=timeout_seconds)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    channel = root.find("channel")
    if channel is None:
        return stats

    for item in channel.findall("item")[:item_limit]:
        stats.records_in += 1
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip() or None
        guid = (item.findtext("guid") or "").strip() or link or title
        description = (item.findtext("description") or "").strip()
        pub_dt = _parse_rss_datetime(item.findtext("pubDate"))

        if not guid:
            stats.records_failed += 1
            continue

        content_hash = hashlib.sha256(f"{title}\n{description}\n{link or ''}".encode("utf-8")).hexdigest()

        existing = db.execute(
            select(RawIngestEvent).where(
                RawIngestEvent.source_id == source.id,
                RawIngestEvent.external_id == guid,
            )
        ).scalar_one_or_none()

        if existing:
            continue

        record = RawIngestEvent(
            source_id=source.id,
            external_id=guid,
            fetched_at=now,
            published_at=pub_dt,
            url=link,
            title=title or None,
            raw_text=description or None,
            raw_json={"title": title, "link": link, "guid": guid, "description": description},
            content_hash=content_hash,
        )
        db.add(record)
        stats.records_ok += 1

    return stats

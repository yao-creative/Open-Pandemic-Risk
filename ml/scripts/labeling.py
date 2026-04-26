from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable


@dataclass(frozen=True)
class EmergencyRow:
    publication_dt: datetime
    emergency_start_dt: datetime | None
    emergency_rating: str


def normalize_emergency_rating(value: str | None) -> str:
    text = (value or "").strip().lower()
    if not text:
        return "unknown"
    if "grade 3" in text:
        return "grade_3_plus"
    if "grade 2" in text:
        return "grade_2"
    if "grade 1" in text:
        return "grade_1"
    if text == "grade":
        return "grade_unknown"
    return text.replace(" ", "_")


def grade3_plus_flag(normalized_rating: str) -> int:
    return int(normalized_rating == "grade_3_plus")


def has_future_start_within(
    publication_dt: datetime,
    all_start_times: Iterable[datetime],
    *,
    window_hours: int,
) -> int:
    upper = publication_dt + timedelta(hours=window_hours)
    for start_dt in all_start_times:
        if publication_dt < start_dt <= upper:
            return 1
    return 0

from __future__ import annotations

from app.settings import Settings


def allowed_tables(settings: Settings) -> set[str]:
    return {item.strip() for item in settings.agent_allowed_tables_csv.split(",") if item.strip()}


def enforce_limit(*, requested: int | None, max_limit: int) -> int:
    if requested is None:
        return max_limit
    return min(max(requested, 1), max_limit)

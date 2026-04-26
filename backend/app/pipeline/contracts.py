from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from app.settings import Settings


@dataclass
class StageInput:
    db: Session
    settings: Settings
    pipeline_name: str
    pipeline_run_id: int | None = None


@dataclass
class StageOutput:
    stage: str
    records_in: int = 0
    records_ok: int = 0
    records_failed: int = 0
    records_skipped: int = 0
    error: str | None = None


class PipelineStage(Protocol):
    name: str

    def run(self, stage_input: StageInput) -> StageOutput:
        ...

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.settings import Settings


@dataclass
class StageContext:
    db: Session
    settings: Settings
    pipeline_run_id: int
    artifacts: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class StageResult:
    status: str
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class StageValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


class PipelineStage:
    name: str
    required_inputs: tuple[str, ...] = ()

    def validate(self, context: StageContext) -> StageValidationResult:
        missing = [key for key in self.required_inputs if context.artifacts.get(key) in (None, "")]
        if missing:
            return StageValidationResult(valid=False, errors=[f"missing required inputs: {', '.join(missing)}"])
        return StageValidationResult(valid=True)

    def run(self, context: StageContext) -> StageResult:
        raise NotImplementedError

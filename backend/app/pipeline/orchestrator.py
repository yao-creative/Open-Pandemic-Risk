from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace

from app.pipeline.contracts import PipelineStage, StageInput, StageOutput


ExceptionClassifier = Callable[[Exception], str]


class PipelineOrchestrator:
    def __init__(self, classify_exception: ExceptionClassifier):
        self._classify_exception = classify_exception

    def run(self, stage_input: StageInput, stages: Sequence[PipelineStage]) -> list[StageOutput]:
        results: list[StageOutput] = []

        for stage in stages:
            try:
                with stage_input.db.begin_nested():
                    output = stage.run(stage_input)
                results.append(replace(output, stage=stage.name))
            except Exception as exc:
                stage_input.db.rollback()
                results.append(
                    StageOutput(
                        stage=stage.name,
                        error=self._classify_exception(exc),
                    )
                )

        return results

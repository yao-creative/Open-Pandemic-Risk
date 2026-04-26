from __future__ import annotations

import pytest

from app.pipeline.contracts import PipelineStage, StageInput, StageOutput
from app.pipeline.orchestrator import PipelineOrchestrator
from app.settings import Settings


class _FakeNested:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeDb:
    def __init__(self):
        self.rollback_calls = 0

    def begin_nested(self):
        return _FakeNested()

    def rollback(self):
        self.rollback_calls += 1


class _StageOk(PipelineStage):
    name = "stage_ok"

    def run(self, stage_input: StageInput) -> StageOutput:
        return StageOutput(
            stage=self.name,
            records_in=10,
            records_ok=8,
            records_failed=1,
            records_skipped=1,
        )


class _StageError(PipelineStage):
    name = "stage_error"

    def run(self, stage_input: StageInput) -> StageOutput:
        raise ValueError("bad payload")


@pytest.mark.unit
def test_orchestrator_runs_successful_stage():
    fake_db = _FakeDb()
    stage_input = StageInput(db=fake_db, settings=Settings(), pipeline_name="test")

    results = PipelineOrchestrator(classify_exception=lambda exc: f"classified:{exc}").run(
        stage_input=stage_input,
        stages=[_StageOk()],
    )

    assert len(results) == 1
    assert results[0].stage == "stage_ok"
    assert results[0].records_in == 10
    assert results[0].records_ok == 8
    assert results[0].records_failed == 1
    assert results[0].records_skipped == 1
    assert results[0].error is None
    assert fake_db.rollback_calls == 0


@pytest.mark.unit
def test_orchestrator_captures_stage_exception():
    fake_db = _FakeDb()
    stage_input = StageInput(db=fake_db, settings=Settings(), pipeline_name="test")

    results = PipelineOrchestrator(classify_exception=lambda exc: f"classified:{exc}").run(
        stage_input=stage_input,
        stages=[_StageError()],
    )

    assert len(results) == 1
    assert results[0].stage == "stage_error"
    assert results[0].records_in == 0
    assert results[0].records_ok == 0
    assert results[0].records_failed == 0
    assert results[0].records_skipped == 0
    assert results[0].error == "classified:bad payload"
    assert fake_db.rollback_calls == 1

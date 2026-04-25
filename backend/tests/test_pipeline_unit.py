import pytest

from app.pipeline.run_ingest import SourceRunResult, _determine_run_status


@pytest.mark.unit
def test_status_ok_when_no_errors():
    status = _determine_run_status(
        [
            SourceRunResult("promed", 1, 1, 0, 0, None),
            SourceRunResult("who_odata", 10, 10, 0, 0, None),
        ]
    )
    assert status == "ok"


@pytest.mark.unit
def test_status_partial_when_one_source_fails():
    status = _determine_run_status(
        [
            SourceRunResult("promed", 0, 0, 0, 0, "auth_error: bad token"),
            SourceRunResult("who_odata", 10, 5, 0, 5, None),
        ]
    )
    assert status == "partial"


@pytest.mark.unit
def test_status_error_when_all_sources_fail():
    status = _determine_run_status(
        [
            SourceRunResult("promed", 0, 0, 0, 0, "auth_error: bad token"),
            SourceRunResult("who_odata", 0, 0, 0, 0, "http_5xx: upstream error"),
        ]
    )
    assert status == "error"

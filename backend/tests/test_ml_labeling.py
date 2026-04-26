from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from ml.scripts.labeling import grade3_plus_flag, has_future_start_within, normalize_emergency_rating


def test_normalize_emergency_rating() -> None:
    assert normalize_emergency_rating("Grade 3") == "grade_3_plus"
    assert normalize_emergency_rating("Grade 3 regional emergency") == "grade_3_plus"
    assert normalize_emergency_rating("") == "unknown"


def test_grade3_plus_flag() -> None:
    assert grade3_plus_flag("grade_3_plus") == 1
    assert grade3_plus_flag("grade_2") == 0


def test_has_future_start_within_window() -> None:
    base = datetime(2024, 8, 1, 0, 0, tzinfo=timezone.utc)
    starts = [
        datetime(2024, 8, 1, 20, 0, tzinfo=timezone.utc),
        datetime(2024, 8, 4, 0, 0, tzinfo=timezone.utc),
    ]

    assert has_future_start_within(base, starts, window_hours=24) == 1
    assert has_future_start_within(base, starts, window_hours=12) == 0

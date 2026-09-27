"""Year inference: the quietest trap in this tool, since texts omit the year."""
from __future__ import annotations

import pytest

from smsledger.util import won, year_for


@pytest.mark.parametrize(
    "ts,month,day,expected",
    [
        ("2026-09-27 10:00:00", 9, 20, 2026),   # earlier the same year
        ("2026-09-27 10:00:00", 9, 27, 2026),   # same day
        ("2027-01-03 09:00:00", 12, 28, 2026),  # last December, received in January
        ("2026-01-01 00:30:00", 12, 31, 2025),  # just past midnight
        ("2026-09-27 10:00:00", 2, 30, 2026),   # impossible date: keep received year
    ],
)
def test_year_for(ts: str, month: int, day: int, expected: int) -> None:
    assert year_for(ts, month, day) == expected


def test_year_for_without_ts_does_not_crash() -> None:
    assert isinstance(year_for("", 9, 20), int)


@pytest.mark.parametrize("raw,expected", [("1,234", 1234), ("0", 0), ("", None), ("abc", None), (None, None)])
def test_won(raw, expected) -> None:
    """None, never 0, when an amount cannot be read."""
    assert won(raw) == expected

from datetime import date, timedelta

import pytest

from app.models import CalibrationState
from app.routers.reports import csv_safe
from app.services.calibration import compute_state

TODAY = date(2026, 11, 5)


@pytest.mark.parametrize(
    "requires, due, expected",
    [
        (False, None, CalibrationState.NOT_REQUIRED),
        (False, date(2020, 1, 1), CalibrationState.NOT_REQUIRED),
        (True, None, CalibrationState.EXPIRED),
        (True, TODAY - timedelta(days=1), CalibrationState.EXPIRED),
        (True, TODAY, CalibrationState.DUE_SOON),
        (True, TODAY + timedelta(days=30), CalibrationState.DUE_SOON),
        (True, TODAY + timedelta(days=31), CalibrationState.VALID),
    ],
)
def test_compute_state(requires, due, expected):
    assert compute_state(requires, due, TODAY) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("=1+1", "'=1+1"),
        ("+5", "'+5"),
        ("-5", "'-5"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("normal text", "normal text"),
        (None, ""),
        (True, "true"),
        (False, "false"),
        (42, "42"),
        (date(2026, 11, 5), "2026-11-05"),
        (CalibrationState.VALID, "valid"),
    ],
)
def test_csv_safe(value, expected):
    assert csv_safe(value) == expected
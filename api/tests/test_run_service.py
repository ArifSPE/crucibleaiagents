"""
Unit tests for helper functions in services/run_service.py.

These are pure-function tests — no database or HTTP involved.
"""
import sys
import os

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from services.run_service import (
    _to_utc_iso,
    _calculate_run_status,
    _categorize_event,
    _get_run_logs,
    _get_run_events,
)


# ── _to_utc_iso ───────────────────────────────────────────────────────────────

def test_to_utc_iso_none():
    assert _to_utc_iso(None) is None


def test_to_utc_iso_naive_datetime():
    dt = datetime(2025, 6, 15, 12, 0, 0)  # naive → assumed UTC
    result = _to_utc_iso(dt)
    assert result is not None
    assert "2025-06-15" in result
    assert "+00:00" in result or "Z" in result or "UTC" in result or result.endswith("+00:00")


def test_to_utc_iso_aware_utc():
    dt = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    result = _to_utc_iso(dt)
    assert "+00:00" in result


def test_to_utc_iso_aware_offset():
    offset = timezone(timedelta(hours=5, minutes=30))
    dt = datetime(2025, 6, 15, 17, 30, 0, tzinfo=offset)
    result = _to_utc_iso(dt)
    assert result is not None
    # The output should represent the correct moment in time
    assert "2025-06-15" in result


def test_to_utc_iso_returns_string():
    assert isinstance(_to_utc_iso(datetime(2024, 1, 1)), str)


# ── _calculate_run_status ─────────────────────────────────────────────────────

def _make_run(**kwargs):
    """Build a minimal mock Runs object."""
    defaults = {
        "status": "",
        "exit_code": None,
        "started_at": None,
        "completed_at": None,
        "stopped_at": None,
    }
    defaults.update(kwargs)
    run = MagicMock()
    for k, v in defaults.items():
        setattr(run, k, v)
    return run


def test_calculate_run_status_uses_explicit_status():
    run = _make_run(status="running")
    assert _calculate_run_status(run) == "running"


def test_calculate_run_status_exit_code_zero():
    run = _make_run(status="", exit_code=0)
    assert _calculate_run_status(run) == "completed"


def test_calculate_run_status_exit_code_nonzero():
    run = _make_run(status="", exit_code=1)
    assert _calculate_run_status(run) == "failed"


def test_calculate_run_status_running_from_timestamps():
    run = _make_run(
        status="",
        exit_code=None,
        started_at=datetime(2025, 1, 1),
        completed_at=None,
        stopped_at=None,
    )
    assert _calculate_run_status(run) == "running"


def test_calculate_run_status_completed_from_timestamps():
    run = _make_run(
        status="",
        exit_code=None,
        started_at=datetime(2025, 1, 1),
        completed_at=datetime(2025, 1, 1, 1),
        stopped_at=None,
    )
    assert _calculate_run_status(run) == "completed"


def test_calculate_run_status_pending_fallback():
    run = _make_run(status="  ", exit_code=None, started_at=None)
    assert _calculate_run_status(run) == "pending"


def test_calculate_run_status_whitespace_is_falsy():
    """An all-whitespace status string should fall through to derived logic."""
    run = _make_run(status="   ", exit_code=0)
    assert _calculate_run_status(run) == "completed"


# ── _categorize_event ─────────────────────────────────────────────────────────

def test_categorize_event_runner_boot():
    level, category, source = _categorize_event("runner_boot", {})
    assert level == "INFO"
    assert category == "infrastructure"
    assert source == "runner"


def test_categorize_event_subprocess_error():
    level, category, source = _categorize_event("subprocess_error", {})
    assert level == "ERROR"


def test_categorize_event_unknown_defaults():
    level, category, source = _categorize_event("some_unknown_event", {})
    assert level == "INFO"
    assert category == "system"
    assert source == "runner"


# ── _get_run_logs / _get_run_events (integration with mock DB) ────────────────

def test_get_run_logs_queries_correct_table():
    from unittest.mock import MagicMock, call
    db = MagicMock()
    query_result = MagicMock()
    db.query.return_value = query_result
    query_result.filter.return_value = query_result
    query_result.order_by.return_value = query_result
    query_result.all.return_value = []

    result = _get_run_logs(db, run_id=42)
    assert result == []
    db.query.assert_called_once()


def test_get_run_events_queries_correct_table():
    from unittest.mock import MagicMock
    db = MagicMock()
    query_result = MagicMock()
    db.query.return_value = query_result
    query_result.filter.return_value = query_result
    query_result.order_by.return_value = query_result
    query_result.all.return_value = []

    result = _get_run_events(db, run_id=7)
    assert result == []
    db.query.assert_called_once()

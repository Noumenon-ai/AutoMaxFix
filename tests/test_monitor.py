from __future__ import annotations

import shlex
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from automaxfix.models import Ticket
from automaxfix.monitor import filter_recent_tickets, find_monitorable, monitor_once
from automaxfix.ticket import create_regression_ticket, load_ticket


def _python_command(script: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"


def _passed_ticket(
    *,
    ticket_id: str = "AMF-20260601-001",
    created_at: str = "2026-06-01T12:00:00+00:00",
    verification_command: str | None,
    status: str = "passed",
) -> Ticket:
    return Ticket(
        id=ticket_id,
        created_at=created_at,
        source="pytest",
        title="Fix calculator regression",
        bug_report="calculator test failed",
        status=status,
        suspected_files=["calculator.py"],
        reproduction_command="pytest tests/test_calculator.py -v",
        verification_command=verification_command,
    )


def test_find_monitorable_only_returns_passed_tickets_with_verification_command() -> (
    None
):
    tickets = [
        _passed_ticket(verification_command="echo ok"),
        _passed_ticket(ticket_id="AMF-20260601-002", verification_command=""),
        _passed_ticket(ticket_id="AMF-20260601-003", verification_command=None),
        _passed_ticket(
            ticket_id="AMF-20260601-004",
            verification_command="echo skipped",
            status="failed",
        ),
    ]

    monitorable = find_monitorable(tickets)

    assert [ticket.id for ticket in monitorable] == ["AMF-20260601-001"]


def test_monitor_once_returns_non_regressed_result_when_verification_still_passes(
    tmp_path: Path,
) -> None:
    ticket = _passed_ticket(verification_command=_python_command("raise SystemExit(0)"))

    results = monitor_once([ticket], tmp_path)

    assert len(results) == 1
    assert results[0].ticket_id == ticket.id
    assert results[0].regressed is False
    assert results[0].returncode == 0
    assert results[0].output_excerpt == ""


def test_monitor_once_detects_regression_and_create_regression_ticket(
    tmp_path: Path,
) -> None:
    ticket = _passed_ticket(
        verification_command=_python_command(
            "import sys; print('boom'); raise SystemExit(9)"
        )
    )

    results = monitor_once([ticket], tmp_path)

    assert len(results) == 1
    result = results[0]
    assert result.ticket_id == ticket.id
    assert result.regressed is True
    assert result.returncode == 9
    assert "boom" in result.output_excerpt

    fixed_now = datetime(2026, 6, 2, 15, 0, tzinfo=timezone.utc)
    regression_ticket, regression_path = create_regression_ticket(
        ticket,
        tmp_path,
        output_excerpt=result.output_excerpt,
        returncode=result.returncode,
        now=fixed_now,
    )

    reloaded = load_ticket(regression_path)
    assert regression_ticket.source == "regression"
    assert regression_ticket.regressed_from == ticket.id
    assert regression_ticket.verification_command == ticket.verification_command
    assert regression_ticket.reproduction_command == ticket.reproduction_command
    assert regression_ticket.suspected_files == ticket.suspected_files
    assert regression_ticket.created_at == fixed_now.replace(microsecond=0).isoformat()
    assert reloaded == regression_ticket
    assert "previously passed" in regression_ticket.bug_report
    assert "boom" in regression_ticket.bug_report


def test_filter_recent_tickets_uses_since_days_window() -> None:
    now = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
    recent = _passed_ticket(
        ticket_id="AMF-20260602-001",
        created_at=(now - timedelta(days=2)).isoformat(),
        verification_command="echo recent",
    )
    stale = _passed_ticket(
        ticket_id="AMF-20260520-001",
        created_at=(now - timedelta(days=20)).isoformat(),
        verification_command="echo stale",
    )

    filtered = filter_recent_tickets([recent, stale], since_days=7, now=now)

    assert [ticket.id for ticket in filtered] == [recent.id]


def test_monitor_once_uses_sanitized_minimal_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AMF_TEST_SECRET", "sk-zzzzzzzzzz")
    ticket = _passed_ticket(
        verification_command=_python_command(
            "import os; secret = os.environ.get('AMF_TEST_SECRET', ''); raise SystemExit(0 if not secret else 9)"
        )
    )

    results = monitor_once([ticket], tmp_path)

    assert len(results) == 1
    assert results[0].regressed is False
    assert results[0].returncode == 0


def test_ticket_regressed_from_round_trips_through_to_dict_and_from_dict() -> None:
    ticket = Ticket(
        id="AMF-20260602-010",
        created_at="2026-06-02T12:00:00+00:00",
        source="regression",
        title="Regression: Fix calculator regression",
        bug_report="verification failed again",
        regressed_from="AMF-20260601-001",
        verification_command="pytest tests/test_calculator.py -v",
    )

    payload = ticket.to_dict()
    reloaded = Ticket.from_dict(payload)
    legacy = Ticket.from_dict(
        {
            "id": "AMF-20260602-011",
            "created_at": "2026-06-02T12:00:00+00:00",
            "source": "pytest",
            "title": "Legacy ticket",
            "bug_report": "bug report",
        }
    )

    assert payload["regressed_from"] == "AMF-20260601-001"
    assert reloaded == ticket
    assert legacy.regressed_from is None

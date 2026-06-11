from __future__ import annotations

import json
from pathlib import Path

import pytest

from automaxfix.models import ParsedFailure
from automaxfix.ticket import (
    TicketIntegrityError,
    create_bug_ticket,
    create_pytest_ticket,
    load_ticket,
)


def test_create_bug_ticket_persists_json(tmp_path: Path) -> None:
    ticket, path = create_bug_ticket("reminder gets duplicated after update", tmp_path)
    assert ticket.id.startswith("AMF-")
    assert path.exists()
    reloaded = load_ticket(path)
    assert reloaded.title == "reminder gets duplicated after update"
    assert reloaded.source == "user"


def test_create_pytest_ticket_tracks_suspected_file(tmp_path: Path) -> None:
    failure = ParsedFailure(
        node_id="tests/test_tasks.py::test_task_does_not_repeat",
        message="AssertionError: duplicate row created",
        suspected_file="tests/test_tasks.py",
    )
    ticket, path = create_pytest_ticket(failure, tmp_path)
    assert path.exists()
    assert ticket.suspected_files == ["tests/test_tasks.py"]


def test_load_ticket_rejects_tampered_checksum(tmp_path: Path) -> None:
    _, path = create_bug_ticket("original bug report", tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["bug_report"] = "tampered bug report"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(TicketIntegrityError, match="integrity"):
        load_ticket(path)


def test_load_ticket_accepts_legacy_ticket_without_checksum(tmp_path: Path) -> None:
    path = tmp_path / "AMF-20260601-001.json"
    path.write_text(
        json.dumps(
            {
                "id": "AMF-20260601-001",
                "created_at": "2026-06-01T12:00:00+00:00",
                "source": "user",
                "title": "Legacy ticket",
                "bug_report": "legacy ticket without checksum",
            }
        ),
        encoding="utf-8",
    )

    ticket = load_ticket(path)
    assert ticket.id == "AMF-20260601-001"
    assert ticket.title == "Legacy ticket"

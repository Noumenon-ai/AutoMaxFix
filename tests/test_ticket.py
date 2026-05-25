from __future__ import annotations

from pathlib import Path

from automaxfix.models import ParsedFailure
from automaxfix.ticket import create_bug_ticket, create_pytest_ticket, load_ticket


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

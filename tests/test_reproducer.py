from __future__ import annotations

from pathlib import Path

from automaxfix.models import RepoContext, Ticket
from automaxfix.reproducer import describe_reproduction_step, suggest_reproduction_test_path


def _ticket() -> Ticket:
    return Ticket(
        id="AMF-20260520-001",
        created_at="2026-05-20T00:00:00+00:00",
        source="user",
        title="Reminder duplicates after update",
        bug_report="Reminder duplicates after update",
    )


def test_suggest_reproduction_test_path_uses_ticket_id() -> None:
    path = suggest_reproduction_test_path(_ticket())
    assert path.startswith("tests/repro/test_amf_20260520_001_")
    assert path.endswith(".py")


def test_describe_reproduction_step_mentions_suspected_file() -> None:
    ticket = _ticket()
    ticket.reproduction_test = suggest_reproduction_test_path(ticket)
    context = RepoContext(
        repo_root=Path("."),
        top_level_entries=[],
        suspected_files=[{"path": "src/reminders.py", "excerpt": "def update(): ..."}],
    )
    description = describe_reproduction_step(ticket, context)
    assert ticket.reproduction_test in description
    assert "src/reminders.py" in description

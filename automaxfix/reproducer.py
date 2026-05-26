from __future__ import annotations

from .models import RepoContext, Ticket
from .utils import slugify


def suggest_reproduction_test_path(ticket: Ticket) -> str:
    suffix = slugify(ticket.title, max_length=24)
    return f"tests/repro/test_{ticket.id.lower().replace('-', '_')}_{suffix}.py"


def describe_reproduction_step(ticket: Ticket, repo_context: RepoContext) -> str:
    suspected = (
        ", ".join(item["path"] for item in repo_context.suspected_files)
        or "unknown files"
    )
    return (
        f"Create or confirm a targeted reproduction test for ticket {ticket.id}. "
        f"Suggested location: {ticket.reproduction_test or suggest_reproduction_test_path(ticket)}. "
        f"Start with suspected files: {suspected}."
    )

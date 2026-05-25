from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .models import Config, FailureRecord, ParsedFailure, Ticket
from .utils import ensure_directory, read_json, slugify, utc_now_iso, write_json


def resolve_tickets_dir(repo_root: Path, config: Config) -> Path:
    path = Path(config.tickets_dir)
    if path.is_absolute():
        return ensure_directory(path)
    return ensure_directory(repo_root / path)


def next_ticket_id(tickets_dir: Path, *, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d")
    prefix = f"AMF-{stamp}-"
    sequence = 0
    for candidate in tickets_dir.glob(f"{prefix}*.json"):
        suffix = candidate.stem.removeprefix(prefix)
        if suffix.isdigit():
            sequence = max(sequence, int(suffix))
    return f"{prefix}{sequence + 1:03d}"


def save_ticket(ticket: Ticket, tickets_dir: Path) -> Path:
    ensure_directory(tickets_dir)
    path = tickets_dir / f"{ticket.id}.json"
    write_json(path, ticket.to_dict())
    return path


def load_ticket(path: Path) -> Ticket:
    return Ticket.from_dict(read_json(path))


def create_bug_ticket(
    bug_report: str,
    tickets_dir: Path,
    *,
    severity: int = 1,
    github_actions_run_url: str | None = None,
) -> tuple[Ticket, Path]:
    title = bug_report.strip().splitlines()[0][:120] or "Untitled bug report"
    ticket = Ticket(
        id=next_ticket_id(tickets_dir),
        created_at=utc_now_iso(),
        source="user",
        title=title,
        bug_report=bug_report.strip(),
        github_actions_run_url=github_actions_run_url,
        severity=severity,
    )
    return ticket, save_ticket(ticket, tickets_dir)


def create_ticket_from_failures(
    failures: list[FailureRecord],
    tickets_dir: Path,
    source: str,
    *,
    severity: int = 1,
    github_actions_run_url: str | None = None,
) -> list[tuple[Ticket, Path]]:
    created: list[tuple[Ticket, Path]] = []
    for failure in failures:
        ticket = Ticket(
            id=next_ticket_id(tickets_dir),
            created_at=utc_now_iso(),
            source=source,
            title=f"Fix failing test {failure.test_id}",
            bug_report=f"{failure.test_id} failed: {failure.error_summary}",
            github_actions_run_url=github_actions_run_url,
            severity=severity,
            suspected_files=[failure.file_path] if failure.file_path else [],
        )
        created.append((ticket, save_ticket(ticket, tickets_dir)))
    return created


def create_pytest_ticket(
    failure: ParsedFailure,
    tickets_dir: Path,
    *,
    severity: int = 1,
    github_actions_run_url: str | None = None,
) -> tuple[Ticket, Path]:
    record = FailureRecord(
        test_id=failure.node_id,
        file_path=failure.suspected_file,
        line=None,
        error_summary=failure.message,
        raw_excerpt=f"{failure.node_id} - {failure.message}",
    )
    return create_ticket_from_failures(
        [record],
        tickets_dir,
        "pytest",
        severity=severity,
        github_actions_run_url=github_actions_run_url,
    )[0]


def suggest_ticket_filename(ticket: Ticket) -> str:
    return f"{ticket.id}-{slugify(ticket.title)}.json"

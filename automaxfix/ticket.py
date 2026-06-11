from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .models import Config, FailureRecord, ParsedFailure, Ticket
from .reliability import ticket_content_checksum, verify_ticket_checksum
from .sanitize import sanitize_mapping
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
    payload = sanitize_mapping(ticket.to_dict())
    payload["content_sha256"] = ticket_content_checksum(payload)
    write_json(path, payload)
    return path


class TicketIntegrityError(RuntimeError):
    """Raised when a ticket's stored integrity checksum does not match."""


def load_ticket(path: Path) -> Ticket:
    payload = read_json(path)
    if isinstance(payload, dict) and "content_sha256" in payload:
        # Legacy tickets without a checksum field are tolerated; a ticket that
        # carries a checksum which no longer matches its content was modified
        # outside AutoMaxFix and must not be trusted.
        if not verify_ticket_checksum(payload):
            raise TicketIntegrityError(
                f"Ticket {path} failed its integrity check: the stored "
                "content_sha256 does not match the ticket content. Refusing to "
                "load a tampered ticket. Recreate the ticket or remove the file."
            )
    return Ticket.from_dict(payload)


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


def create_regression_ticket(
    original_ticket: Ticket,
    tickets_dir: Path,
    *,
    output_excerpt: str,
    returncode: int,
    now: datetime | None = None,
    github_actions_run_url: str | None = None,
) -> tuple[Ticket, Path]:
    created_at = (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    bug_report_lines = [
        f"Ticket {original_ticket.id} previously passed but its verification now fails.",
        f"Original ticket: {original_ticket.id}",
        f"Verification command: {original_ticket.verification_command or ''}",
        f"Latest verification exit: {returncode}",
    ]
    if original_ticket.reproduction_command:
        bug_report_lines.append(
            f"Reproduction command: {original_ticket.reproduction_command}"
        )
    if output_excerpt:
        bug_report_lines.extend(["Output excerpt:", output_excerpt])
    ticket = Ticket(
        id=next_ticket_id(tickets_dir, now=now),
        created_at=created_at,
        source="regression",
        title=f"Regression: {original_ticket.title}",
        bug_report="\n".join(bug_report_lines),
        github_actions_run_url=github_actions_run_url,
        severity=original_ticket.severity,
        suspected_files=list(original_ticket.suspected_files),
        reproduction_command=original_ticket.reproduction_command,
        verification_command=original_ticket.verification_command,
        regressed_from=original_ticket.id,
    )
    return ticket, save_ticket(ticket, tickets_dir)


def create_ticket_from_failures(
    failures: list[FailureRecord],
    tickets_dir: Path,
    source: str,
    *,
    severity: int = 1,
    github_actions_run_url: str | None = None,
    reproduction_command: str | None = None,
    verification_command: str | None = None,
    check_definition: dict[str, object] | None = None,
    bug_report_details: str | None = None,
) -> list[tuple[Ticket, Path]]:
    created: list[tuple[Ticket, Path]] = []
    title_prefix = "Fix failing check" if source == "check" else "Fix failing test"
    for failure in failures:
        bug_report = f"{failure.test_id} failed: {failure.error_summary}"
        if bug_report_details:
            bug_report = f"{bug_report}\n{bug_report_details}"
        ticket = Ticket(
            id=next_ticket_id(tickets_dir),
            created_at=utc_now_iso(),
            source=source,
            title=f"{title_prefix} {failure.test_id}",
            bug_report=bug_report,
            github_actions_run_url=github_actions_run_url,
            severity=severity,
            suspected_files=[failure.file_path] if failure.file_path else [],
            reproduction_command=reproduction_command,
            verification_command=verification_command,
            check_definition=check_definition,
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

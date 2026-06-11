from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .checks import CheckDefinition, run_check
from .models import CommandResult, Config, Ticket
from .utils import run_command, tail_text


@dataclass(slots=True)
class MonitorResult:
    ticket_id: str
    regressed: bool
    returncode: int
    output_excerpt: str


def find_monitorable(tickets: list[Ticket]) -> list[Ticket]:
    return [
        ticket
        for ticket in tickets
        if ticket.status == "passed"
        and ticket.verification_command is not None
        and ticket.verification_command.strip() != ""
    ]


def filter_recent_tickets(
    tickets: list[Ticket],
    since_days: int | None,
    *,
    now: datetime | None = None,
) -> list[Ticket]:
    if since_days is None:
        return list(tickets)
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=since_days)
    return [
        ticket
        for ticket in tickets
        if (created_at := _parse_created_at(ticket.created_at)) is None
        or created_at >= cutoff
    ]


def monitor_once(
    tickets: list[Ticket],
    repo_root: Path,
    *,
    now: datetime | None = None,
    timeout_seconds: int | None = None,
) -> list[MonitorResult]:
    del now
    effective_timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else Config().agent.timeout_seconds
    )
    results: list[MonitorResult] = []
    for ticket in find_monitorable(tickets):
        if ticket.check_definition is not None:
            results.append(_monitor_check_ticket(ticket, repo_root))
            continue
        result = _run_verification(
            ticket.verification_command or "",
            repo_root,
            timeout_seconds=effective_timeout,
        )
        results.append(
            MonitorResult(
                ticket_id=ticket.id,
                regressed=result.returncode != 0,
                returncode=result.returncode,
                output_excerpt=_build_output_excerpt(result),
            )
        )
    return results


def _monitor_check_ticket(ticket: Ticket, repo_root: Path) -> MonitorResult:
    """Re-apply full check semantics for check-sourced tickets.

    Exit code alone loses the pattern semantics of matches/not_matches
    checks (for example `cat app.log` exits 0 even when the log still
    contains ERROR), so the original CheckDefinition is re-run instead.
    """
    try:
        check = CheckDefinition.from_dict(ticket.check_definition or {})
    except (TypeError, ValueError) as exc:
        return MonitorResult(
            ticket_id=ticket.id,
            regressed=True,
            returncode=-1,
            output_excerpt=f"Ticket check_definition is invalid: {exc}",
        )
    outcome = run_check(check, repo_root)
    excerpt = _build_output_excerpt(outcome.command_result)
    if outcome.failure is not None:
        summary = f"Check {check.name!r} failed: {outcome.failure.error_summary}"
        excerpt = f"{summary}\n{excerpt}" if excerpt else summary
    return MonitorResult(
        ticket_id=ticket.id,
        regressed=outcome.failure is not None,
        returncode=outcome.command_result.returncode,
        output_excerpt=excerpt,
    )


def _parse_created_at(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _run_verification(
    command: str, repo_root: Path, *, timeout_seconds: int
) -> CommandResult:
    try:
        return run_command(
            ["sh", "-c", command],
            cwd=repo_root,
            timeout_seconds=timeout_seconds,
            allow_full_env=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CommandResult(
            command=command,
            returncode=124,
            stdout=stdout,
            stderr=stderr,
        )


def _build_output_excerpt(result: CommandResult) -> str:
    combined_output = _combine_output(result.stdout, result.stderr).strip()
    if not combined_output:
        return ""
    return tail_text(combined_output, max_chars=1200)


def _combine_output(stdout: str, stderr: str) -> str:
    if stdout and stderr and not stdout.endswith("\n"):
        return f"{stdout}\n{stderr}"
    return stdout + stderr

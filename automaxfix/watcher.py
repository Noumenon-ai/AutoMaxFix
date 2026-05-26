from __future__ import annotations

import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TextIO

from .models import ApprovalDecision, CommandResult, Config
from .safety import SafetyError, split_safe_command
from .ticket import Ticket
from .utils import ensure_directory


class WatchError(RuntimeError):
    """Raised when watch mode cannot start safely."""


@dataclass(slots=True)
class WatchSummary:
    polls: int = 0
    passes: int = 0
    failures: int = 0
    tickets_created: int = 0
    patch_runs: int = 0
    approvals_granted: int = 0
    approvals_denied: int = 0
    last_status: str = "NOT RUN"
    last_timestamp: str | None = None
    last_ticket_path: Path | None = None
    failure_logs: list[Path] = field(default_factory=list)


@dataclass(slots=True)
class WatchRuntime:
    subprocess_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
    input_fn: Callable[[str], str] = input
    sleep_fn: Callable[[float], None] = time.sleep
    now_fn: Callable[[], float] = time.time
    monotonic_fn: Callable[[], float] = time.monotonic
    signal_module: Any = signal
    output: TextIO = field(default_factory=lambda: sys.stdout)


class _WatchConsole:
    def __init__(self, output: TextIO) -> None:
        self._output = output
        self._progress_active = False

    def update_status(self, status: str, timestamp: str) -> None:
        self._output.write(f"\r[watch] last run: {status} @ {timestamp}")
        self._output.flush()
        self._progress_active = True

    def line(self, text: str = "") -> None:
        if self._progress_active:
            self._output.write("\n")
            self._progress_active = False
        self._output.write(text + "\n")
        self._output.flush()

    def write_block(self, text: str) -> None:
        if self._progress_active:
            self._output.write("\n")
            self._progress_active = False
        self._output.write(text)
        if text and not text.endswith("\n"):
            self._output.write("\n")
        self._output.flush()


class _StopController:
    def __init__(self) -> None:
        self.stop_requested = False

    def handle_sigint(self, signum: int, frame: object) -> None:
        del signum, frame
        self.stop_requested = True


def _validate_watch_request(config: Config, test_runner: str) -> None:
    if not config.watch_mode.enabled:
        raise WatchError("Watch mode is disabled by config.")
    if test_runner not in config.watch_mode.allowed_runners:
        allowed = ", ".join(config.watch_mode.allowed_runners) or "(none)"
        raise WatchError(
            f"Test runner {test_runner!r} is not allowed by watch_mode.allowed_runners: {allowed}"
        )


def _timestamp(now: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(now))


def _capture_path(
    logs_dir: Path, test_runner: str, poll_number: int, now: float
) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    return logs_dir / f"watch_{test_runner}_{stamp}_{poll_number:04d}.log"


def _run_test_command(
    command: str,
    *,
    cwd: Path,
    subprocess_run: Callable[..., subprocess.CompletedProcess[str]],
    monotonic_fn: Callable[[], float],
) -> CommandResult:
    try:
        argv = split_safe_command(command)
    except SafetyError as exc:
        raise WatchError(str(exc)) from exc

    started = monotonic_fn()
    completed = subprocess_run(
        argv,
        cwd=str(cwd),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    duration_seconds = monotonic_fn() - started
    return CommandResult(
        command=" ".join(argv),
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr="",
        duration_seconds=duration_seconds,
    )


def _build_approval_callback(
    *,
    config: Config,
    console: _WatchConsole,
    runtime: WatchRuntime,
    summary: WatchSummary,
) -> Callable[..., ApprovalDecision]:
    def approval_callback(**kwargs: object) -> ApprovalDecision:
        patch_text = str(kwargs.get("patch_text", ""))
        ticket = kwargs.get("ticket")
        ticket_id = ticket.id if isinstance(ticket, Ticket) else "unknown"

        if config.watch_mode.auto_approve_in_watch:
            summary.approvals_granted += 1
            console.line(
                f"[watch] auto-approve enabled for {ticket_id}; applying patch."
            )
            return ApprovalDecision(
                approved=True,
                requires_confirmation=False,
                reason="Approved automatically in watch mode.",
            )

        console.line(f"[watch] proposed diff for {ticket_id}:")
        console.write_block(patch_text)
        while True:
            answer = runtime.input_fn("[watch] apply patch? [y/N] ")
            normalized = answer.strip().lower()
            if normalized in {"y", "yes"}:
                summary.approvals_granted += 1
                return ApprovalDecision(
                    approved=True,
                    requires_confirmation=False,
                    reason="Approved in watch mode.",
                )
            if normalized in {"", "n", "no"}:
                summary.approvals_denied += 1
                return ApprovalDecision(
                    approved=False,
                    requires_confirmation=False,
                    reason="Patch declined in watch mode.",
                )
            console.line("[watch] enter y or n.")

    return approval_callback


def _print_summary(console: _WatchConsole, summary: WatchSummary) -> None:
    console.line("[watch] summary:")
    console.line(f"polls: {summary.polls}")
    console.line(f"passes: {summary.passes}")
    console.line(f"failures: {summary.failures}")
    console.line(f"tickets created: {summary.tickets_created}")
    console.line(f"patch runs: {summary.patch_runs}")
    console.line(f"approvals granted: {summary.approvals_granted}")
    console.line(f"approvals denied: {summary.approvals_denied}")
    console.line(f"last status: {summary.last_status}")


def watch_loop(
    *,
    repo_root: Path,
    config: Config,
    test_runner: str,
    command: str,
    interval: int | None,
    scan_failures: Callable[[str], list[tuple[Ticket, Path]]],
    run_ticket: Callable[[Path, Callable[..., ApprovalDecision]], int],
    runtime: WatchRuntime | None = None,
) -> WatchSummary:
    runtime = runtime or WatchRuntime()
    _validate_watch_request(config, test_runner)
    effective_interval = (
        interval if interval is not None else config.watch_mode.default_interval
    )
    if effective_interval < 1:
        raise WatchError("Watch interval must be >= 1 second.")

    console = _WatchConsole(runtime.output)
    summary = WatchSummary()
    stop = _StopController()
    previous_handler = runtime.signal_module.signal(
        runtime.signal_module.SIGINT, stop.handle_sigint
    )
    logs_dir = ensure_directory(repo_root / ".automaxfix" / "logs")
    approval_callback = _build_approval_callback(
        config=config,
        console=console,
        runtime=runtime,
        summary=summary,
    )

    try:
        while not stop.stop_requested:
            result = _run_test_command(
                command,
                cwd=repo_root,
                subprocess_run=runtime.subprocess_run,
                monotonic_fn=runtime.monotonic_fn,
            )
            now = runtime.now_fn()
            status = "PASS" if result.passed else "FAIL"
            summary.polls += 1
            summary.last_status = status
            summary.last_timestamp = _timestamp(now)
            console.update_status(status, summary.last_timestamp)

            if result.passed:
                summary.passes += 1
            else:
                summary.failures += 1
                capture_path = _capture_path(logs_dir, test_runner, summary.polls, now)
                capture_path.write_text(result.stdout, encoding="utf-8")
                summary.failure_logs.append(capture_path)
                console.line(f"[watch] captured failing output: {capture_path}")
                created = scan_failures(result.stdout)
                summary.tickets_created += len(created)
                if not created:
                    console.line(
                        f"[watch] no failing tests parsed for {test_runner}; continuing."
                    )
                else:
                    ticket, ticket_path = created[0]
                    summary.last_ticket_path = ticket_path
                    console.line(
                        f"[watch] created {len(created)} ticket(s); running {ticket.id}."
                    )
                    if len(created) > 1:
                        console.line(
                            "[watch] additional tickets were left queued for manual review."
                        )
                    summary.patch_runs += 1
                    run_ticket(ticket_path, approval_callback)

            if stop.stop_requested:
                break
            runtime.sleep_fn(effective_interval)
    finally:
        runtime.signal_module.signal(runtime.signal_module.SIGINT, previous_handler)
        console.line()
        _print_summary(console, summary)

    return summary

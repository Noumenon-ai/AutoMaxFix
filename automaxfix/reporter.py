from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .models import AgentAttempt, CommandResult, Config, Ticket
from .utils import ensure_directory, tail_text


def resolve_reports_dir(repo_root: Path, config: Config) -> Path:
    path = Path(config.reports_dir)
    if path.is_absolute():
        return ensure_directory(path)
    return ensure_directory(repo_root / path)


def _render_command_result(result: CommandResult | None) -> str:
    if result is None:
        return "- Not run"
    stdout_tail = tail_text(result.stdout) or "(empty)"
    stderr_tail = tail_text(result.stderr) or "(empty)"
    return (
        f"- command: {result.command}\n"
        f"  exit_code: {result.returncode}\n"
        f"  duration_seconds: {result.duration_seconds:.3f}\n"
        f"  stdout_tail: {stdout_tail}\n"
        f"  stderr_tail: {stderr_tail}"
    )


def _render_attempts(attempts: list[AgentAttempt]) -> str:
    if not attempts:
        return "- None"
    lines: list[str] = []
    for attempt in attempts:
        validation = "valid diff" if attempt.is_valid_diff else "invalid diff"
        retryable = "retryable" if attempt.retryable_invalid_diff else "not retryable"
        command = attempt.command or "manual patch file"
        output_file = (
            str(attempt.output_file) if attempt.output_file is not None else "n/a"
        )
        strategy = attempt.strategy.value if attempt.strategy is not None else "n/a"
        lines.append(
            f"- attempt {attempt.attempt_number}: strategy={strategy}, {validation}, {retryable}, command={command}, output={output_file}"
        )
        if attempt.validation_errors:
            for error in attempt.validation_errors:
                lines.append(f"  validation_error: {error}")
    return "\n".join(lines)


def build_report_markdown(
    *,
    ticket: Ticket,
    agent_used: str,
    attempt_count: int,
    invalid_diff_retries: int,
    reproduction_before_patch: str,
    final_diff_validation: str,
    safety_gates: str,
    files_changed: list[str],
    approval: str,
    targeted_test: CommandResult | None,
    regression_test: CommandResult | None,
    final_verdict: str,
    rollback_instructions: str,
    next_step: str,
    attempts: list[AgentAttempt],
) -> str:
    changed = (
        "\n".join(f"- {item}" for item in files_changed) if files_changed else "- None"
    )
    run_url_line = ""
    if ticket.github_actions_run_url:
        run_url_line = f"GitHub Actions run: {ticket.github_actions_run_url}\n"
    return (
        "# AutoMaxFix Phase 3 Report\n\n"
        f"Ticket: {ticket.id}\n"
        f"Status: {ticket.status}\n"
        f"Agent used: {agent_used}\n"
        f"Attempt count: {attempt_count}\n"
        f"Invalid diff retries: {invalid_diff_retries}\n"
        f"Bug: {ticket.bug_report}\n"
        f"{run_url_line}"
        f"Reproduction before patch: {reproduction_before_patch}\n"
        f"Final diff validation: {final_diff_validation}\n"
        f"Safety gates passed/failed: {safety_gates}\n"
        f"Files changed:\n{changed}\n"
        f"Approval: {approval}\n"
        f"Attempt log:\n{_render_attempts(attempts)}\n"
        f"Targeted tests:\n{_render_command_result(targeted_test)}\n"
        f"Regression:\n{_render_command_result(regression_test)}\n"
        f"Final verdict: {final_verdict}\n"
        f"Rollback instructions: {rollback_instructions}\n"
        f"Next step: {next_step}\n"
    )


def write_report(
    *,
    repo_root: Path,
    config: Config,
    ticket: Ticket,
    agent_used: str,
    attempt_count: int,
    invalid_diff_retries: int,
    reproduction_before_patch: str,
    final_diff_validation: str,
    safety_gates: str,
    files_changed: list[str],
    approval: str,
    targeted_test: CommandResult | None,
    regression_test: CommandResult | None,
    final_verdict: str,
    rollback_instructions: str,
    next_step: str,
    attempts: list[AgentAttempt] | None = None,
) -> Path:
    reports_dir = resolve_reports_dir(repo_root, config)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_path = reports_dir / f"{timestamp}-{ticket.id}.md"
    report_path.write_text(
        build_report_markdown(
            ticket=ticket,
            agent_used=agent_used,
            attempt_count=attempt_count,
            invalid_diff_retries=invalid_diff_retries,
            reproduction_before_patch=reproduction_before_patch,
            final_diff_validation=final_diff_validation,
            safety_gates=safety_gates,
            files_changed=files_changed,
            approval=approval,
            targeted_test=targeted_test,
            regression_test=regression_test,
            final_verdict=final_verdict,
            rollback_instructions=rollback_instructions,
            next_step=next_step,
            attempts=attempts or [],
        ),
        encoding="utf-8",
    )
    return report_path


def latest_report_path(repo_root: Path, config: Config) -> Path | None:
    reports_dir = resolve_reports_dir(repo_root, config)
    candidates = sorted(reports_dir.glob("*.md"))
    if not candidates:
        return None
    return candidates[-1]

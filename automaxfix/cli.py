from __future__ import annotations

import argparse
import time
from dataclasses import replace
from pathlib import Path
from typing import Callable

from .agent_runner import AgentRunError, build_agent_prompt, load_patch_from_file, run_agent_patch
from .approval import evaluate_approval
from .config import load_config, write_default_config
from .models import (
    AgentAttempt,
    ApprovalDecision,
    CommandResult,
    Config,
    PatchValidationResult,
    StrategyName,
    TicketStrategyAttempt,
)
from .patch_parser import validate_patch_text
from .patcher import inspect_repo
from .reporter import latest_report_path, resolve_reports_dir, write_report
from .reproducer import describe_reproduction_step, suggest_reproduction_test_path
from .scanners import SCANNERS
from .test_runner import run_regression_suite, run_targeted_test
from .ticket import (
    create_bug_ticket,
    create_ticket_from_failures,
    load_ticket,
    resolve_tickets_dir,
    save_ticket,
)
from .utils import ensure_directory, github_actions_run_url, resolve_path, tail_text
from .workspace import (
    WorkspaceError,
    apply_patch,
    create_pre_patch_backup,
    get_workspace_status,
    require_git_repo,
    reverse_patch,
    write_patch_artifact,
)
from .watcher import WatchError, watch_loop
from .safety import resolve_repo_root


_STRATEGY_LADDER = (
    StrategyName.MINIMAL,
    StrategyName.TEST_FIRST,
    StrategyName.REFACTOR,
    StrategyName.ROLLBACK,
)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("Value must be >= 1.")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="automaxfix", description="Controlled repair loop for AI-built software.")
    parser.add_argument("--config", help="Path to config file.", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create .automaxfix scaffolding.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite config.yml if it already exists.")

    scan_parser = subparsers.add_parser("scan", help="Create tickets from test runner output.")
    scan_group = scan_parser.add_mutually_exclusive_group(required=True)
    scan_group.add_argument("--pytest-output", help="Path to captured pytest output.")
    scan_group.add_argument("--jest-output", help="Path to captured Jest output.")
    scan_group.add_argument("--vitest-output", help="Path to captured Vitest output.")
    scan_group.add_argument("--mocha-output", help="Path to captured Mocha output.")
    scan_group.add_argument("--go-output", help="Path to captured go test output.")
    scan_group.add_argument("--cargo-output", help="Path to captured cargo test output.")
    scan_group.add_argument("--from-file", help="Path to captured test output for any registered format.")
    scan_parser.add_argument("--format", choices=sorted(SCANNERS), help="Format name for --from-file.")

    bug_parser = subparsers.add_parser("bug", help="Create a ticket from a bug report.")
    bug_parser.add_argument("bug_report", help="Plain-English bug report.")

    reproduce_parser = subparsers.add_parser("reproduce", help="Prepare a reproduction brief for one ticket.")
    reproduce_parser.add_argument("--ticket", required=True, help="Path to a ticket JSON file.")

    run_parser = subparsers.add_parser("run", help="Run the safe patch loop for one ticket.")
    run_parser.add_argument("--ticket", required=True, help="Path to a ticket JSON file.")
    run_parser.add_argument("--patch-file", help="Unified diff file to apply in manual patch mode.")
    run_parser.add_argument(
        "--agent",
        choices=["manual_patch_file", "codex_cli", "claude_cli"],
        help="Override the configured agent mode.",
    )
    run_parser.add_argument(
        "--max-attempts",
        type=_positive_int,
        default=3,
        help="Maximum strategy attempts for agent repair mode (default: 3).",
    )
    run_parser.add_argument("--no-repro", action="store_true", help="Skip the reproduction check.")
    run_parser.add_argument("--yes", action="store_true", help="Approve the proposed patch and apply it.")

    watch_parser = subparsers.add_parser("watch", help="Poll a test command and auto-run repairs.")
    watch_parser.add_argument("--test-runner", required=True, help="Scanner/runtime name used to parse failures.")
    watch_parser.add_argument("--command", dest="watch_command", required=True, help="Test command to poll.")
    watch_parser.add_argument(
        "--interval",
        type=_positive_int,
        default=None,
        help="Polling interval in seconds (default: config.watch_mode.default_interval).",
    )

    report_parser = subparsers.add_parser("report", help="Print the latest report.")
    report_parser.add_argument("--latest", action="store_true", help="Show the latest report.")

    subparsers.add_parser("status", help="Show current AutoMaxFix status.")

    metrics_parser = subparsers.add_parser(
        "metrics", help="Summarize the local ticket archive."
    )
    metrics_parser.add_argument(
        "--since-days",
        type=_positive_int,
        default=None,
        help="Limit to tickets created in the last N days.",
    )
    metrics_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text).",
    )

    backup_parser = subparsers.add_parser(
        "backup", help="Archive .automaxfix/ to a timestamped tarball."
    )
    backup_parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to write the archive into (default: backups/ inside repo).",
    )
    return parser


def _automaxfix_dir(repo_root: Path) -> Path:
    return ensure_directory(repo_root / ".automaxfix")


def _logs_dir(repo_root: Path) -> Path:
    return ensure_directory(_automaxfix_dir(repo_root) / "logs")


def _max_invalid_diff_attempts(config: Config, agent_mode: str) -> int:
    if agent_mode == "manual_patch_file":
        return 1
    return max(1, min(config.patch.max_patch_attempts, 3))


def _ci_run_url(config: Config) -> str | None:
    if not config.ci_mode:
        return None
    return github_actions_run_url()


def _safety_summary(
    *,
    reproduction: str,
    diff_validation: str,
    workspace: str,
    approval: str,
    patch_apply: str,
) -> str:
    return (
        f"reproduction={reproduction}; "
        f"diff_validation={diff_validation}; "
        f"workspace={workspace}; "
        f"approval={approval}; "
        f"patch_apply={patch_apply}"
    )


def _validation_summary(validation: PatchValidationResult) -> str:
    if validation.valid:
        return f"passed; validated unified diff touching {len(validation.files_changed)} file(s)."
    if validation.errors:
        return "failed; " + "; ".join(validation.errors)
    return "failed; unknown diff validation error."


def _strategy_attempts(ticket, max_attempts: int) -> list[StrategyName]:
    exhausted = ticket.strategy_memo.exhausted_strategies()
    return [strategy for strategy in _STRATEGY_LADDER if strategy not in exhausted][:max_attempts]


def _record_strategy_attempt(
    *,
    ticket,
    strategy: StrategyName,
    reason: str,
    agent_used: str,
    duration_sec: float,
    succeeded: bool,
) -> None:
    ticket.strategy_memo.attempts.append(
        TicketStrategyAttempt(
            strategy=strategy,
            reason=reason,
            agent_used=agent_used,
            duration_sec=duration_sec,
            succeeded=succeeded,
        )
    )


def _validation_failure_reason(validation: PatchValidationResult) -> str:
    if validation.errors:
        return "Patch validation failed: " + "; ".join(validation.errors)
    return "Patch validation failed."


def _command_failure_detail(result: CommandResult) -> str:
    detail = tail_text(result.stderr.strip() or result.stdout.strip(), max_chars=400)
    if detail:
        return detail
    return f"exit {result.returncode}"


def _post_patch_failure_reason(
    *,
    targeted_after: CommandResult | None,
    regression_result: CommandResult,
) -> str:
    if targeted_after is not None and not targeted_after.passed:
        return "Targeted tests failed after patch: " + _command_failure_detail(targeted_after)
    if not regression_result.passed:
        return "Regression suite failed after patch: " + _command_failure_detail(regression_result)
    return "Patch applied but one or more post-patch checks failed."


def _last_strategy_failure(ticket) -> str:
    last_attempt = ticket.strategy_memo.last_attempt()
    if last_attempt is not None and last_attempt.reason:
        return last_attempt.reason
    return "No strategies remaining for this ticket."


def _agent_attempt_tag(ticket_id: str, strategy_number: int, strategy: StrategyName) -> str:
    return f"{ticket_id}-s{strategy_number:02d}-{strategy.value}"


def _run_strategy_agent_loop(
    *,
    agent_mode: str,
    repo_root: Path,
    config: Config,
    ticket,
    repo_context,
    attempts: list[AgentAttempt],
    strategy: StrategyName,
) -> tuple[PatchValidationResult, str, str, int]:
    max_invalid_attempts = _max_invalid_diff_attempts(config, agent_mode)
    retry_errors: list[str] | None = None
    validation: PatchValidationResult | None = None
    final_patch_text = ""
    agent_used = agent_mode
    invalid_diff_retries = 0

    for retry_index in range(max_invalid_attempts):
        attempt = run_agent_patch(
            mode=agent_mode,
            repo_root=repo_root,
            logs_dir=_logs_dir(repo_root),
            config=config,
            ticket=ticket,
            repo_context=repo_context,
            strategy=strategy,
            attempt_number=len(attempts) + 1,
            validation_errors=retry_errors,
        )
        validation = validate_patch_text(attempt.stdout, repo_root=repo_root, config=config)
        attempt.is_valid_diff = validation.valid
        attempt.validation_errors = list(validation.errors)
        attempt.retryable_invalid_diff = validation.retryable_invalid_diff
        attempts.append(attempt)
        agent_used = attempt.agent_used
        final_patch_text = attempt.stdout

        if validation.valid:
            invalid_diff_retries = retry_index
            break
        if not validation.retryable_invalid_diff or retry_index + 1 == max_invalid_attempts:
            invalid_diff_retries = retry_index
            break
        retry_errors = list(validation.errors)

    assert validation is not None
    return validation, final_patch_text, agent_used, invalid_diff_retries


def _init_command(base_dir: Path, *, force: bool) -> int:
    automaxfix_dir = ensure_directory(base_dir / ".automaxfix")
    ensure_directory(automaxfix_dir / "tickets")
    ensure_directory(automaxfix_dir / "reports")
    ensure_directory(automaxfix_dir / "logs")
    config_path = automaxfix_dir / "config.yml"
    if force or not config_path.exists():
        write_default_config(config_path)
    print(f"AutoMaxFix initialized at {automaxfix_dir}")
    print(f"Config: {config_path}")
    return 0


def _scan_output_text(
    *,
    repo_root: Path,
    config: Config,
    source: str,
    output_text: str,
):
    tickets_dir = resolve_tickets_dir(repo_root, config)
    failures = SCANNERS[source](output_text, repo_root)
    if not failures:
        return []
    return create_ticket_from_failures(
        failures,
        tickets_dir,
        source,
        github_actions_run_url=_ci_run_url(config),
    )


def _scan_command(base_dir: Path, config_path: str | None, source: str, output_path: str) -> int:
    config = load_config(base_dir, config_path)
    repo_root = resolve_repo_root(base_dir, config)
    resolved_path = resolve_path(base_dir, output_path)
    created = _scan_output_text(
        repo_root=repo_root,
        config=config,
        source=source,
        output_text=resolved_path.read_text(encoding="utf-8"),
    )
    if not created:
        if source == "pytest":
            print("No failing tests found in pytest output.")
        else:
            print(f"No failing tests found in {source} output.")
        return 0
    print(f"Created {len(created)} ticket(s).")
    for ticket, path in created:
        print(f"- {ticket.id}: {path}")
    return 0


def _resolve_scan_source(args: argparse.Namespace, parser: argparse.ArgumentParser) -> tuple[str, str]:
    source_flags = {
        "pytest": args.pytest_output,
        "jest": args.jest_output,
        "vitest": args.vitest_output,
        "mocha": args.mocha_output,
        "go": args.go_output,
        "cargo": args.cargo_output,
    }
    for source, output_path in source_flags.items():
        if output_path:
            if args.format:
                parser.error("--format can only be used with --from-file.")
            return source, output_path

    if args.from_file:
        if not args.format:
            parser.error("--format is required with --from-file.")
        return args.format, args.from_file

    parser.error("One scan source is required.")
    raise AssertionError("unreachable")


def _bug_command(base_dir: Path, config_path: str | None, bug_report: str) -> int:
    config = load_config(base_dir, config_path)
    repo_root = resolve_repo_root(base_dir, config)
    tickets_dir = resolve_tickets_dir(repo_root, config)
    ticket, path = create_bug_ticket(
        bug_report,
        tickets_dir,
        github_actions_run_url=_ci_run_url(config),
    )
    print(f"Created ticket {ticket.id}")
    print(path)
    return 0


def _report_command(base_dir: Path, config_path: str | None, latest: bool) -> int:
    del latest
    config = load_config(base_dir, config_path)
    repo_root = resolve_repo_root(base_dir, config)
    report_path = latest_report_path(repo_root, config)
    if report_path is None:
        print("No reports found.")
        return 0
    print(report_path)
    print()
    print(report_path.read_text(encoding="utf-8"))
    return 0


def _status_command(base_dir: Path, config_path: str | None) -> int:
    config = load_config(base_dir, config_path)
    repo_root = resolve_repo_root(base_dir, config)
    workspace = get_workspace_status(repo_root)
    tickets_dir = resolve_tickets_dir(repo_root, config)
    reports_dir = resolve_reports_dir(repo_root, config)
    ticket_count = len(list(tickets_dir.glob("*.json")))
    report_count = len(list(reports_dir.glob("*.md")))
    print(f"Repo path: {repo_root}")
    print(f"Git repo: {'yes' if workspace.is_git_repo else 'no'}")
    print(f"Workspace: {'dirty' if workspace.is_dirty else 'clean'}")
    if workspace.status_lines:
        print("Workspace changes:")
        for line in workspace.status_lines:
            print(f"- {line}")
    print(f"Agent mode: {config.agent.mode}")
    print(f"Configured max patch attempts: {config.patch.max_patch_attempts}")
    if config.agent.mode != "manual_patch_file":
        print(f"Active attempts for current mode: {_max_invalid_diff_attempts(config, config.agent.mode)}")
    print(f"Tickets: {ticket_count}")
    print(f"Reports: {report_count}")
    return 0


def _reproduce_command(base_dir: Path, config_path: str | None, ticket_path: str) -> int:
    config = load_config(base_dir, config_path)
    repo_root = resolve_repo_root(base_dir, config)
    ticket = load_ticket(resolve_path(base_dir, ticket_path))
    if not ticket.reproduction_test:
        ticket.reproduction_test = suggest_reproduction_test_path(ticket)
        save_ticket(ticket, resolve_tickets_dir(repo_root, config))
    repo_context = inspect_repo(ticket, repo_root)
    prompt_mode = config.agent.mode if config.agent.mode in {"codex_cli", "claude_cli"} else "codex_cli"
    prompt = build_agent_prompt(
        mode=prompt_mode,
        ticket=ticket,
        repo_context=repo_context,
        config=config,
        reproduction_test=ticket.reproduction_test,
    )
    prompt_path = _logs_dir(repo_root) / f"reproduce_{ticket.id}.prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    print("No reproduction test file created.")
    print(describe_reproduction_step(ticket, repo_context))
    print(prompt_path)
    return 0


def _write_report(
    *,
    repo_root: Path,
    config: Config,
    ticket,
    agent_used: str,
    attempt_count: int,
    invalid_diff_retries: int,
    reproduction_before_patch: str,
    final_diff_validation: str,
    safety_gates: str,
    files_changed: list[str],
    approval: str,
    targeted_test,
    regression_test,
    final_verdict: str,
    rollback_instructions: str,
    next_step: str,
    attempts: list[AgentAttempt],
) -> Path:
    return write_report(
        repo_root=repo_root,
        config=config,
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
        attempts=attempts,
    )


def _run_command_with_config(
    base_dir: Path,
    config: Config,
    ticket_path: str,
    *,
    patch_file: str | None,
    agent_override: str | None,
    max_attempts: int,
    skip_repro: bool,
    approved: bool,
    approval_callback: Callable[..., ApprovalDecision] | None = None,
) -> int:
    repo_root = resolve_repo_root(base_dir, config)
    ticket = load_ticket(resolve_path(base_dir, ticket_path))
    run_url = _ci_run_url(config)
    if run_url:
        ticket.github_actions_run_url = run_url
    repo_context = inspect_repo(ticket, repo_root)
    tickets_dir = resolve_tickets_dir(repo_root, config)

    agent_mode = "manual_patch_file" if patch_file else (agent_override or config.agent.mode)
    agent_used = agent_mode
    attempts: list[AgentAttempt] = []
    reproduction_before_patch = "Skipped via --no-repro."
    targeted_before = None

    if config.require_reproduction_test and not skip_repro:
        if not ticket.reproduction_test or not (repo_root / ticket.reproduction_test).exists():
            message = "No reproduction test found. Create reproduction test before patching."
            ticket.result = message
            save_ticket(ticket, tickets_dir)
            report_path = _write_report(
                repo_root=repo_root,
                config=config,
                ticket=ticket,
                agent_used=agent_used,
                attempt_count=0,
                invalid_diff_retries=0,
                reproduction_before_patch=message,
                final_diff_validation="not run",
                safety_gates=_safety_summary(
                    reproduction="failed",
                    diff_validation="not run",
                    workspace="not run",
                    approval="not run",
                    patch_apply="not run",
                ),
                files_changed=[],
                approval="Not requested.",
                targeted_test=None,
                regression_test=None,
                final_verdict="FAIL",
                rollback_instructions="No patch was applied.",
                next_step="Run `python3 -m automaxfix.cli reproduce --ticket ...` and create the failing test first.",
                attempts=attempts,
            )
            print(message)
            print(report_path)
            return 0

        targeted_before = run_targeted_test(config, repo_root, ticket.reproduction_test)
        if targeted_before.passed:
            message = "Reproduction test passed before patch. Expected it to fail."
            ticket.result = message
            ticket.status = "failed"
            ticket.tests_run = [targeted_before.command]
            save_ticket(ticket, tickets_dir)
            report_path = _write_report(
                repo_root=repo_root,
                config=config,
                ticket=ticket,
                agent_used=agent_used,
                attempt_count=0,
                invalid_diff_retries=0,
                reproduction_before_patch=message,
                final_diff_validation="not run",
                safety_gates=_safety_summary(
                    reproduction="failed",
                    diff_validation="not run",
                    workspace="not run",
                    approval="not run",
                    patch_apply="not run",
                ),
                files_changed=[],
                approval="Not requested.",
                targeted_test=targeted_before,
                regression_test=None,
                final_verdict="FAIL",
                rollback_instructions="No patch was applied.",
                next_step="Fix the reproduction so it fails before patching.",
                attempts=attempts,
            )
            print(message)
            print(report_path)
            return 0

        reproduction_before_patch = (
            f"Failed as expected via {targeted_before.command} (exit {targeted_before.returncode})."
        )
        ticket.status = "reproduced"
        save_ticket(ticket, tickets_dir)

    reproduction_gate = "passed" if skip_repro or targeted_before is not None else "not run"
    validation: PatchValidationResult | None = None
    final_diff_validation = "not run"
    files_changed: list[str] = []
    total_invalid_diff_retries = 0
    approval_text = "Not requested."
    rollback_instructions = "No patch was applied."
    next_step = "Inspect the failing test output and prepare a new patch attempt."
    final_message = ""
    targeted_after = None
    regression_result = None
    diff_validation_gate = "not run"
    workspace_gate = "not run"
    approval_gate = "not run"
    patch_apply_gate = "not run"
    persist_strategy_memo = patch_file is None
    strategy_plan = [StrategyName.MINIMAL] if patch_file else _strategy_attempts(ticket, max_attempts)

    if not strategy_plan:
        final_message = _last_strategy_failure(ticket)
        ticket.result = final_message
        ticket.status = "failed"
        save_ticket(ticket, tickets_dir)
        report_path = _write_report(
            repo_root=repo_root,
            config=config,
            ticket=ticket,
            agent_used=agent_used,
            attempt_count=len(attempts),
            invalid_diff_retries=total_invalid_diff_retries,
            reproduction_before_patch=reproduction_before_patch,
            final_diff_validation=final_diff_validation,
            safety_gates=_safety_summary(
                reproduction=reproduction_gate,
                diff_validation=diff_validation_gate,
                workspace=workspace_gate,
                approval=approval_gate,
                patch_apply=patch_apply_gate,
            ),
            files_changed=files_changed,
            approval=approval_text,
            targeted_test=targeted_before,
            regression_test=regression_result,
            final_verdict="FAIL",
            rollback_instructions=rollback_instructions,
            next_step="All configured strategies have already been exhausted for this ticket.",
            attempts=attempts,
        )
        print(final_message)
        print(report_path)
        return 0

    for run_strategy_number, strategy in enumerate(strategy_plan, start=1):
        strategy_started_at = time.monotonic()
        validation = None
        final_diff_validation = "not run"
        files_changed = []
        approval_text = "Not requested."
        rollback_instructions = "No patch was applied."
        targeted_after = None
        regression_result = None
        diff_validation_gate = "not run"
        workspace_gate = "not run"
        approval_gate = "not run"
        patch_apply_gate = "not run"
        final_patch_text = ""

        try:
            if patch_file:
                patch_result = load_patch_from_file(resolve_path(base_dir, patch_file))
                final_patch_text = patch_result.patch_text
                manual_attempt = AgentAttempt(
                    attempt_number=len(attempts) + 1,
                    mode="manual_patch_file",
                    agent_used="manual_patch_file",
                    strategy=strategy,
                    output_file=resolve_path(base_dir, patch_file),
                    stdout=patch_result.patch_text,
                )
                validation = validate_patch_text(final_patch_text, repo_root=repo_root, config=config)
                manual_attempt.is_valid_diff = validation.valid
                manual_attempt.validation_errors = list(validation.errors)
                manual_attempt.retryable_invalid_diff = False
                attempts.append(manual_attempt)
                agent_used = "manual_patch_file"
            else:
                validation, final_patch_text, agent_used, invalid_diff_retries = _run_strategy_agent_loop(
                    agent_mode=agent_mode,
                    repo_root=repo_root,
                    config=config,
                    ticket=ticket,
                    repo_context=repo_context,
                    attempts=attempts,
                    strategy=strategy,
                )
                total_invalid_diff_retries += invalid_diff_retries
        except AgentRunError as exc:
            final_message = str(exc)
            ticket.result = final_message
            ticket.status = "failed"
            save_ticket(ticket, tickets_dir)
            report_path = _write_report(
                repo_root=repo_root,
                config=config,
                ticket=ticket,
                agent_used=agent_used,
                attempt_count=len(attempts),
                invalid_diff_retries=total_invalid_diff_retries,
                reproduction_before_patch=reproduction_before_patch,
                final_diff_validation=final_diff_validation,
                safety_gates=_safety_summary(
                    reproduction=reproduction_gate,
                    diff_validation=diff_validation_gate,
                    workspace=workspace_gate,
                    approval=approval_gate,
                    patch_apply=patch_apply_gate,
                ),
                files_changed=files_changed,
                approval=approval_text,
                targeted_test=targeted_before,
                regression_test=regression_result,
                final_verdict="FAIL",
                rollback_instructions=rollback_instructions,
                next_step="Fix the agent command or supply --patch-file.",
                attempts=attempts,
            )
            print(final_message)
            print(report_path)
            return 0

        assert validation is not None
        final_diff_validation = _validation_summary(validation)
        files_changed = validation.files_changed

        if not validation.valid:
            diff_validation_gate = "failed"
            final_message = _validation_failure_reason(validation)
            ticket.status = "failed"
            ticket.result = final_message
            ticket.patch_summary = None
            ticket.tests_run = [targeted_before.command] if targeted_before is not None else []
            save_ticket(ticket, tickets_dir)
            report_path = _write_report(
                repo_root=repo_root,
                config=config,
                ticket=ticket,
                agent_used=agent_used,
                attempt_count=len(attempts),
                invalid_diff_retries=total_invalid_diff_retries,
                reproduction_before_patch=reproduction_before_patch,
                final_diff_validation=final_diff_validation,
                safety_gates=_safety_summary(
                    reproduction=reproduction_gate,
                    diff_validation=diff_validation_gate,
                    workspace=workspace_gate,
                    approval=approval_gate,
                    patch_apply=patch_apply_gate,
                ),
                files_changed=files_changed,
                approval=approval_text,
                targeted_test=targeted_before,
                regression_test=regression_result,
                final_verdict="FAIL",
                rollback_instructions=rollback_instructions,
                next_step="Revise the patch so it passes unified-diff validation.",
                attempts=attempts,
            )
            print(final_message)
            print(report_path)
            return 0

        diff_validation_gate = "passed"

        try:
            workspace = require_git_repo(repo_root)
            workspace_gate = "passed"
        except WorkspaceError as exc:
            final_message = str(exc)
            ticket.result = final_message
            ticket.status = "failed"
            save_ticket(ticket, tickets_dir)
            report_path = _write_report(
                repo_root=repo_root,
                config=config,
                ticket=ticket,
                agent_used=agent_used,
                attempt_count=len(attempts),
                invalid_diff_retries=total_invalid_diff_retries,
                reproduction_before_patch=reproduction_before_patch,
                final_diff_validation=final_diff_validation,
                safety_gates=_safety_summary(
                    reproduction=reproduction_gate,
                    diff_validation=diff_validation_gate,
                    workspace="failed",
                    approval=approval_gate,
                    patch_apply=patch_apply_gate,
                ),
                files_changed=files_changed,
                approval=approval_text,
                targeted_test=targeted_before,
                regression_test=regression_result,
                final_verdict="FAIL",
                rollback_instructions=rollback_instructions,
                next_step="Run Phase 3 inside a git repository.",
                attempts=attempts,
            )
            print(final_message)
            print(report_path)
            return 0

        if approval_callback is not None:
            approval = approval_callback(
                config=config,
                ticket=ticket,
                patch_text=final_patch_text,
                validation=validation,
                workspace=workspace,
            )
        else:
            approval = evaluate_approval(config, approved=approved, workspace_dirty=workspace.is_dirty)
        approval_text = approval.reason
        if workspace.is_dirty and workspace.status_lines:
            approval_text += " Existing changes: " + ", ".join(workspace.status_lines[:10])
        if not approval.approved:
            final_message = approval.reason
            approval_gate = "failed"
            ticket.result = final_message
            ticket.status = "failed"
            save_ticket(ticket, tickets_dir)
            report_path = _write_report(
                repo_root=repo_root,
                config=config,
                ticket=ticket,
                agent_used=agent_used,
                attempt_count=len(attempts),
                invalid_diff_retries=total_invalid_diff_retries,
                reproduction_before_patch=reproduction_before_patch,
                final_diff_validation=final_diff_validation,
                safety_gates=_safety_summary(
                    reproduction=reproduction_gate,
                    diff_validation=diff_validation_gate,
                    workspace=workspace_gate,
                    approval=approval_gate,
                    patch_apply=patch_apply_gate,
                ),
                files_changed=files_changed,
                approval=approval_text,
                targeted_test=targeted_before,
                regression_test=regression_result,
                final_verdict="FAIL",
                rollback_instructions=rollback_instructions,
                next_step="Review the files changed and re-run with --yes.",
                attempts=attempts,
            )
            print(final_message)
            print(report_path)
            return 0

        approval_gate = "passed"
        strategy_tag = _agent_attempt_tag(
            ticket.id,
            len(ticket.strategy_memo.attempts) + 1 if persist_strategy_memo else run_strategy_number,
            strategy,
        )
        reports_dir = resolve_reports_dir(repo_root, config)
        backup_path = create_pre_patch_backup(repo_root, reports_dir, strategy_tag)
        applied_patch_path = write_patch_artifact(
            _logs_dir(repo_root),
            strategy_tag,
            final_patch_text,
            github_actions_run_url=run_url,
        )

        try:
            apply_patch(repo_root, final_patch_text)
            patch_apply_gate = "passed"
        except WorkspaceError as exc:
            patch_apply_gate = "failed"
            final_message = str(exc)
            rollback_instructions = f"Reapply the saved pre-patch diff if needed: git apply {backup_path}"
            ticket.status = "failed"
            ticket.result = final_message
            ticket.patch_summary = None
            ticket.tests_run = [targeted_before.command] if targeted_before is not None else []
            save_ticket(ticket, tickets_dir)
            report_path = _write_report(
                repo_root=repo_root,
                config=config,
                ticket=ticket,
                agent_used=agent_used,
                attempt_count=len(attempts),
                invalid_diff_retries=total_invalid_diff_retries,
                reproduction_before_patch=reproduction_before_patch,
                final_diff_validation=final_diff_validation,
                safety_gates=_safety_summary(
                    reproduction=reproduction_gate,
                    diff_validation=diff_validation_gate,
                    workspace=workspace_gate,
                    approval=approval_gate,
                    patch_apply=patch_apply_gate,
                ),
                files_changed=files_changed,
                approval=approval_text,
                targeted_test=targeted_before,
                regression_test=regression_result,
                final_verdict="FAIL",
                rollback_instructions=rollback_instructions,
                next_step="Fix the diff so `git apply --check` passes.",
                attempts=attempts,
            )
            print(final_message)
            print(report_path)
            return 0

        ticket.status = "patched"
        ticket.patch_summary = f"Applied unified diff touching {len(validation.files_changed)} file(s)."

        if ticket.reproduction_test and not skip_repro:
            targeted_after = run_targeted_test(config, repo_root, ticket.reproduction_test)
        regression_result = run_regression_suite(config, repo_root)

        ticket.tests_run = []
        if targeted_before is not None:
            ticket.tests_run.append(targeted_before.command)
        if targeted_after is not None:
            ticket.tests_run.append(targeted_after.command)
        ticket.tests_run.append(regression_result.command)

        passed = (
            (skip_repro or (targeted_before is not None and not targeted_before.passed))
            and validation.valid
            and (targeted_after is None or targeted_after.passed)
            and regression_result.passed
        )
        if passed:
            final_message = "Patch validated, applied, and passed targeted and regression tests."
            ticket.status = "passed"
            ticket.result = final_message
            if persist_strategy_memo:
                _record_strategy_attempt(
                    ticket=ticket,
                    strategy=strategy,
                    reason=final_message,
                    agent_used=agent_used,
                    duration_sec=time.monotonic() - strategy_started_at,
                    succeeded=True,
                )
            save_ticket(ticket, tickets_dir)

            rollback_instructions = f"Reverse the applied patch with: git apply -R {applied_patch_path}"
            if backup_path.stat().st_size:
                rollback_instructions += (
                    f" ; then restore prior working changes with: git apply {backup_path}"
                )

            report_path = _write_report(
                repo_root=repo_root,
                config=config,
                ticket=ticket,
                agent_used=agent_used,
                attempt_count=len(attempts),
                invalid_diff_retries=total_invalid_diff_retries,
                reproduction_before_patch=reproduction_before_patch,
                final_diff_validation=final_diff_validation,
                safety_gates=_safety_summary(
                    reproduction=reproduction_gate,
                    diff_validation=diff_validation_gate,
                    workspace=workspace_gate,
                    approval=approval_gate,
                    patch_apply=patch_apply_gate,
                ),
                files_changed=files_changed,
                approval=approval_text,
                targeted_test=targeted_after,
                regression_test=regression_result,
                final_verdict="PASS",
                rollback_instructions=rollback_instructions,
                next_step="Review the report and commit the change manually.",
                attempts=attempts,
            )
            print(final_message)
            print(report_path)
            return 0

        final_message = _post_patch_failure_reason(
            targeted_after=targeted_after,
            regression_result=regression_result,
        )
        ticket.status = "failed"
        ticket.result = final_message
        ticket.patch_summary = None
        if persist_strategy_memo:
            _record_strategy_attempt(
                ticket=ticket,
                strategy=strategy,
                reason=final_message,
                agent_used=agent_used,
                duration_sec=time.monotonic() - strategy_started_at,
                succeeded=False,
            )
        save_ticket(ticket, tickets_dir)

        try:
            reverse_patch(repo_root, final_patch_text)
        except WorkspaceError as exc:
            final_message = "Post-patch checks failed and rollback failed: " + str(exc)
            rollback_instructions = f"Reverse the applied patch manually with: git apply -R {applied_patch_path}"
            if backup_path.stat().st_size:
                rollback_instructions += (
                    f" ; then restore prior working changes with: git apply {backup_path}"
                )
            ticket.result = final_message
            save_ticket(ticket, tickets_dir)
            report_path = _write_report(
                repo_root=repo_root,
                config=config,
                ticket=ticket,
                agent_used=agent_used,
                attempt_count=len(attempts),
                invalid_diff_retries=total_invalid_diff_retries,
                reproduction_before_patch=reproduction_before_patch,
                final_diff_validation=final_diff_validation,
                safety_gates=_safety_summary(
                    reproduction=reproduction_gate,
                    diff_validation=diff_validation_gate,
                    workspace=workspace_gate,
                    approval=approval_gate,
                    patch_apply=patch_apply_gate,
                ),
                files_changed=files_changed,
                approval=approval_text,
                targeted_test=targeted_after,
                regression_test=regression_result,
                final_verdict="FAIL",
                rollback_instructions=rollback_instructions,
                next_step=next_step,
                attempts=attempts,
            )
            print(final_message)
            print(report_path)
            return 0

        if patch_file:
            break

    if not final_message:
        final_message = _last_strategy_failure(ticket)
    ticket.status = "failed"
    ticket.result = final_message
    save_ticket(ticket, tickets_dir)
    report_path = _write_report(
        repo_root=repo_root,
        config=config,
        ticket=ticket,
        agent_used=agent_used,
        attempt_count=len(attempts),
        invalid_diff_retries=total_invalid_diff_retries,
        reproduction_before_patch=reproduction_before_patch,
        final_diff_validation=final_diff_validation,
        safety_gates=_safety_summary(
            reproduction=reproduction_gate,
            diff_validation=diff_validation_gate,
            workspace=workspace_gate,
            approval=approval_gate,
            patch_apply=patch_apply_gate,
        ),
        files_changed=files_changed,
        approval=approval_text,
        targeted_test=targeted_after if targeted_after is not None else targeted_before,
        regression_test=regression_result,
        final_verdict="FAIL",
        rollback_instructions=rollback_instructions,
        next_step=next_step,
        attempts=attempts,
    )
    print(final_message)
    print(report_path)
    return 0


def _run_command(
    base_dir: Path,
    config_path: str | None,
    ticket_path: str,
    *,
    patch_file: str | None,
    agent_override: str | None,
    max_attempts: int,
    skip_repro: bool,
    approved: bool,
) -> int:
    config = load_config(base_dir, config_path)
    return _run_command_with_config(
        base_dir,
        config,
        ticket_path,
        patch_file=patch_file,
        agent_override=agent_override,
        max_attempts=max_attempts,
        skip_repro=skip_repro,
        approved=approved,
    )


def _watch_command(
    base_dir: Path,
    config_path: str | None,
    *,
    test_runner: str,
    command: str,
    interval: int | None,
) -> int:
    config = load_config(base_dir, config_path)
    if test_runner not in SCANNERS:
        print(f"Unsupported test runner: {test_runner}")
        return 2

    repo_root = resolve_repo_root(base_dir, config)
    watch_config = replace(config, test_command=command)

    def scan_failures(output_text: str):
        return _scan_output_text(
            repo_root=repo_root,
            config=watch_config,
            source=test_runner,
            output_text=output_text,
        )

    def run_ticket(ticket_path: Path, approval_callback: Callable[..., ApprovalDecision]) -> int:
        return _run_command_with_config(
            base_dir,
            watch_config,
            str(ticket_path),
            patch_file=None,
            agent_override="codex_cli",
            max_attempts=2,
            skip_repro=True,
            approved=False,
            approval_callback=approval_callback,
        )

    try:
        watch_loop(
            repo_root=repo_root,
            config=watch_config,
            test_runner=test_runner,
            command=command,
            interval=interval,
            scan_failures=scan_failures,
            run_ticket=run_ticket,
        )
    except WatchError as exc:
        print(str(exc))
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    base_dir = Path.cwd()

    if args.command == "init":
        return _init_command(base_dir, force=args.force)
    if args.command == "scan":
        source, output_path = _resolve_scan_source(args, parser)
        return _scan_command(base_dir, args.config, source, output_path)
    if args.command == "bug":
        return _bug_command(base_dir, args.config, args.bug_report)
    if args.command == "reproduce":
        return _reproduce_command(base_dir, args.config, args.ticket)
    if args.command == "run":
        return _run_command(
            base_dir,
            args.config,
            args.ticket,
            patch_file=args.patch_file,
            agent_override=args.agent,
            max_attempts=args.max_attempts,
            skip_repro=args.no_repro,
            approved=args.yes,
        )
    if args.command == "watch":
        return _watch_command(
            base_dir,
            args.config,
            test_runner=args.test_runner,
            command=args.watch_command,
            interval=args.interval,
        )
    if args.command == "report":
        return _report_command(base_dir, args.config, args.latest)
    if args.command == "status":
        return _status_command(base_dir, args.config)
    if args.command == "metrics":
        return _metrics_command(
            base_dir, args.config, since_days=args.since_days, output_format=args.format
        )
    if args.command == "backup":
        return _backup_command(base_dir, args.config, args.output_dir)
    parser.error(f"Unknown command: {args.command}")
    return 2


def _metrics_command(
    base_dir: Path,
    config_path: str | None,
    *,
    since_days: int | None,
    output_format: str,
) -> int:
    from .config import load_config
    from .metrics import render_json, render_text, summarize
    from .ticket import resolve_tickets_dir

    config = load_config(base_dir, config_path)
    tickets_dir = resolve_tickets_dir(base_dir, config)
    report = summarize(tickets_dir, since_days=since_days)
    if output_format == "json":
        print(render_json(report))
    else:
        print(render_text(report))
    return 0


def _backup_command(
    base_dir: Path,
    config_path: str | None,
    output_dir: str | None,
) -> int:
    import tarfile
    from datetime import datetime, timezone

    state_dir = base_dir / ".automaxfix"
    if not state_dir.is_dir():
        print("ERROR: no .automaxfix/ directory to back up")
        return 1
    destination_root = Path(output_dir) if output_dir else base_dir / "backups"
    destination_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = destination_root / f"automaxfix-{stamp}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(state_dir, arcname=".automaxfix")
    print(f"wrote {archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

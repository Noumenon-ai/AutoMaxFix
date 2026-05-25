from __future__ import annotations

import tempfile
from pathlib import Path

from .models import AgentAttempt, AgentRunResult, Config, RepoContext, StrategyName, Ticket
from .prompt_templates import build_claude_prompt, build_codex_prompt
from .safety import SafetyError, split_safe_command
from .utils import ensure_directory, run_command


class AgentRunError(RuntimeError):
    """Raised when an external coding agent cannot produce a usable patch."""


def build_agent_prompt(
    *,
    mode: str,
    ticket: Ticket,
    repo_context: RepoContext,
    config: Config,
    reproduction_test: str | None,
    strategy: StrategyName = StrategyName.MINIMAL,
    attempt_number: int = 1,
    validation_errors: list[str] | None = None,
) -> str:
    if mode == "codex_cli":
        return build_codex_prompt(
            ticket=ticket,
            repo_context=repo_context,
            config=config,
            reproduction_test=reproduction_test,
            strategy=strategy,
            attempt_number=attempt_number,
            validation_errors=validation_errors,
        )
    if mode == "claude_cli":
        return build_claude_prompt(
            ticket=ticket,
            repo_context=repo_context,
            config=config,
            reproduction_test=reproduction_test,
            strategy=strategy,
            attempt_number=attempt_number,
            validation_errors=validation_errors,
        )
    raise AgentRunError(f"Unsupported agent mode: {mode}")


def _default_agent_command(mode: str) -> str:
    if mode == "codex_cli":
        return "codex"
    if mode == "claude_cli":
        return "claude"
    raise AgentRunError(f"Unsupported agent mode: {mode}")


def _build_agent_argv(
    *,
    mode: str,
    command: str,
    prompt_file: Path,
    prompt_text: str,
) -> list[str]:
    argv = split_safe_command(command)
    placeholder_map = {
        "{prompt_file}": str(prompt_file),
        "{prompt_text}": prompt_text,
    }
    if any(token in placeholder_map for token in argv):
        return [placeholder_map.get(token, token) for token in argv]
    if mode == "codex_cli":
        return argv + ["exec", prompt_text]
    if mode == "claude_cli":
        return argv + ["-p", prompt_text]
    raise AgentRunError(f"Unsupported agent mode: {mode}")


def load_patch_from_file(patch_file: Path) -> AgentRunResult:
    if not patch_file.exists():
        raise AgentRunError(f"Patch file not found: {patch_file}")
    return AgentRunResult(
        mode="manual_patch_file",
        patch_text=patch_file.read_text(encoding="utf-8"),
        agent_used="manual_patch_file",
        patch_file=patch_file,
        command=None,
        attempt_count=1,
        invalid_diff_retries=0,
    )


def run_agent_patch(
    *,
    mode: str,
    repo_root: Path,
    logs_dir: Path,
    config: Config,
    ticket: Ticket,
    repo_context: RepoContext,
    command_override: str | None = None,
    strategy: StrategyName = StrategyName.MINIMAL,
    attempt_number: int = 1,
    validation_errors: list[str] | None = None,
) -> AgentAttempt:
    if mode == "manual_patch_file":
        raise AgentRunError("manual_patch_file mode requires --patch-file.")

    prompt_text = build_agent_prompt(
        mode=mode,
        ticket=ticket,
        repo_context=repo_context,
        config=config,
        reproduction_test=ticket.reproduction_test,
        strategy=strategy,
        attempt_number=attempt_number,
        validation_errors=validation_errors,
    )
    ensure_directory(logs_dir)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".prompt.txt",
        prefix=f"{ticket.id.lower()}_attempt_{attempt_number}_",
        dir=logs_dir,
        delete=False,
    ) as handle:
        handle.write(prompt_text)
        prompt_path = Path(handle.name)

    command = command_override or config.agent.command or _default_agent_command(mode)
    try:
        argv = _build_agent_argv(mode=mode, command=command, prompt_file=prompt_path, prompt_text=prompt_text)
    except SafetyError as exc:
        raise AgentRunError(str(exc)) from exc

    result = run_command(
        argv,
        cwd=repo_root,
        timeout_seconds=config.agent.timeout_seconds,
        pythonpath_root=repo_root,
    )
    if not result.passed:
        raise AgentRunError(result.stderr.strip() or result.stdout.strip() or "Agent command failed.")

    output_file = logs_dir / f"{ticket.id.lower()}_attempt_{attempt_number}.diff"
    output_file.write_text(result.stdout, encoding="utf-8")

    return AgentAttempt(
        attempt_number=attempt_number,
        mode=mode,
        agent_used=mode,
        strategy=strategy,
        prompt_file=prompt_path,
        output_file=output_file,
        command=result.command,
        stdout=result.stdout,
        stderr=result.stderr,
        returncode=result.returncode,
        duration_seconds=result.duration_seconds,
    )


def build_final_agent_result(
    *,
    mode: str,
    patch_text: str,
    attempt: AgentAttempt,
    invalid_diff_retries: int,
) -> AgentRunResult:
    return AgentRunResult(
        mode=mode,
        patch_text=patch_text,
        agent_used=attempt.agent_used,
        prompt_file=attempt.prompt_file,
        command=attempt.command,
        stdout=attempt.stdout,
        stderr=attempt.stderr,
        returncode=attempt.returncode,
        duration_seconds=attempt.duration_seconds,
        attempt_count=attempt.attempt_number,
        invalid_diff_retries=invalid_diff_retries,
        validation_errors=list(attempt.validation_errors),
    )

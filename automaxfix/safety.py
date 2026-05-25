from __future__ import annotations

import shlex
from pathlib import Path

from .models import Config, PatchProposal


class SafetyError(RuntimeError):
    """Raised when AutoMaxFix would perform an unsafe action."""


_BANNED_COMMAND_SNIPPETS = (
    "rm -rf",
    "sudo",
    "curl | bash",
    "wget | bash",
    "chmod -r 777",
    "pip install",
    "npm install",
)

_SHELL_CONTROL_TOKENS = ("|", "&&", "||", ";", "$(", "`", ">", "<")


def resolve_repo_root(base_dir: Path, config: Config) -> Path:
    candidate = Path(config.repo_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_dir / candidate).resolve()


def _ensure_inside_repo(repo_root: Path, candidate: Path) -> Path:
    try:
        candidate.relative_to(repo_root)
    except ValueError as exc:
        raise SafetyError(f"Path {candidate} is outside repo_path {repo_root}") from exc
    return candidate


def _is_sensitive_path(relative_path: Path) -> bool:
    if any(part == ".git" for part in relative_path.parts):
        return True
    if relative_path.name.startswith(".env"):
        return True
    lowered_parts = [part.lower() for part in relative_path.parts]
    if "secrets" in lowered_parts:
        return True
    if "secret" in relative_path.name.lower():
        return True
    return False


def _path_matches_prefix(relative_path: Path, raw_prefix: str) -> bool:
    prefix = Path(raw_prefix)
    if str(prefix) in ("", "."):
        return True
    return relative_path == prefix or prefix in relative_path.parents


def validate_edit_path(repo_root: Path, config: Config, raw_path: str) -> Path:
    candidate = Path(raw_path)
    resolved = candidate.resolve() if candidate.is_absolute() else (repo_root / candidate).resolve()
    _ensure_inside_repo(repo_root, resolved)
    relative_path = resolved.relative_to(repo_root)
    if _is_sensitive_path(relative_path):
        raise SafetyError(f"Editing {relative_path} is blocked")
    if any(_path_matches_prefix(relative_path, item) for item in config.blocked_paths):
        raise SafetyError(f"Editing {relative_path} is blocked by config")
    if not any(_path_matches_prefix(relative_path, item) for item in config.allowed_paths):
        raise SafetyError(f"Editing {relative_path} is outside allowed_paths")
    return resolved


def validate_patch_proposal(
    repo_root: Path, config: Config, proposal: PatchProposal, *, extra_files: int = 0
) -> None:
    file_count = len(proposal.files) + extra_files
    if file_count > config.max_files_changed:
        raise SafetyError(
            f"Patch touches {file_count} files, above max_files_changed={config.max_files_changed}"
        )
    for change in proposal.files:
        validate_edit_path(repo_root, config, change.path)


def reject_shell_controls(command: str) -> None:
    if any(token in command for token in _SHELL_CONTROL_TOKENS):
        raise SafetyError(f"Shell control tokens are blocked: {command}")


def contains_dangerous_text(text: str) -> str | None:
    lowered = text.lower()
    for snippet in _BANNED_COMMAND_SNIPPETS:
        if snippet in lowered:
            return snippet
    return None


def split_safe_command(command: str) -> list[str]:
    reject_shell_controls(command)
    snippet = contains_dangerous_text(command)
    if snippet:
        raise SafetyError(f"Dangerous command rejected: {command}")
    argv = shlex.split(command)
    if not argv:
        raise SafetyError("Empty command is not allowed")
    return argv


def validate_command(
    *,
    command: str,
    config: Config,
    kind: str,
    test_file: str | None = None,
) -> list[str]:
    if kind == "regression":
        expected = config.test_command
    elif kind == "targeted":
        if not test_file:
            raise SafetyError("targeted test command requires test_file")
        expected = config.targeted_test_command.format(test_file=test_file)
    else:
        raise SafetyError(f"Unknown command kind: {kind}")

    if command.strip() != expected.strip():
        raise SafetyError(
            f"Command {command!r} does not match configured {kind} command {expected!r}"
        )

    return split_safe_command(command)

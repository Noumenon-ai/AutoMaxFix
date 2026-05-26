from __future__ import annotations

import tempfile
from pathlib import Path

from .models import WorkspaceStatus
from .utils import ensure_directory, run_command


class WorkspaceError(RuntimeError):
    """Raised when the current repo cannot safely accept a patch."""


def get_workspace_status(repo_root: Path) -> WorkspaceStatus:
    probe = run_command(["git", "rev-parse", "--show-toplevel"], cwd=repo_root)
    if not probe.passed:
        return WorkspaceStatus(repo_root=repo_root, is_git_repo=False, is_dirty=False)

    git_root = Path(probe.stdout.strip()).resolve()
    status = run_command(["git", "status", "--short"], cwd=repo_root)
    status_lines = [line for line in status.stdout.splitlines() if line.strip()]
    return WorkspaceStatus(
        repo_root=repo_root,
        git_root=git_root,
        is_git_repo=True,
        is_dirty=bool(status_lines),
        status_lines=status_lines,
    )


def require_git_repo(repo_root: Path) -> WorkspaceStatus:
    status = get_workspace_status(repo_root)
    if not status.is_git_repo:
        raise WorkspaceError("Patch apply requires a git repo for Phase 2.")
    return status


def create_pre_patch_backup(repo_root: Path, reports_dir: Path, ticket_id: str) -> Path:
    ensure_directory(reports_dir)
    result = run_command(["git", "diff"], cwd=repo_root)
    if not result.passed:
        raise WorkspaceError("Failed to capture pre-patch git diff.")
    backup_path = reports_dir / f"pre_patch_{ticket_id}.diff"
    backup_path.write_text(result.stdout, encoding="utf-8")
    return backup_path


def write_patch_artifact(
    logs_dir: Path,
    ticket_id: str,
    patch_text: str,
    *,
    github_actions_run_url: str | None = None,
) -> Path:
    ensure_directory(logs_dir)
    patch_path = logs_dir / f"applied_{ticket_id}.diff"
    prefix = ""
    if github_actions_run_url:
        prefix = (
            "# AutoMaxFix patch artifact\n"
            f"# GitHub Actions run: {github_actions_run_url}\n\n"
        )
    patch_path.write_text(prefix + patch_text, encoding="utf-8")
    return patch_path


def _apply_patch_text(
    repo_root: Path, patch_text: str, *, reverse: bool = False
) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".diff", delete=False
    ) as handle:
        handle.write(patch_text)
        patch_path = Path(handle.name)
    try:
        check_argv = ["git", "apply"]
        if reverse:
            check_argv.append("-R")
        check_argv.extend(["--check", str(patch_path)])
        check = run_command(check_argv, cwd=repo_root)
        if not check.passed:
            raise WorkspaceError(check.stderr.strip() or "git apply --check failed.")
        apply_argv = ["git", "apply"]
        if reverse:
            apply_argv.append("-R")
        apply_argv.append(str(patch_path))
        applied = run_command(apply_argv, cwd=repo_root)
        if not applied.passed:
            raise WorkspaceError(applied.stderr.strip() or "git apply failed.")
    finally:
        patch_path.unlink(missing_ok=True)


def apply_patch(repo_root: Path, patch_text: str) -> None:
    _apply_patch_text(repo_root, patch_text)


def reverse_patch(repo_root: Path, patch_text: str) -> None:
    _apply_patch_text(repo_root, patch_text, reverse=True)

from __future__ import annotations

from pathlib import Path

from automaxfix.workspace import (
    apply_patch,
    create_pre_patch_backup,
    get_workspace_status,
    require_git_repo,
    write_patch_artifact,
)
from tests.helpers import build_fix_patch, create_phase2_repo


def test_workspace_status_detects_clean_and_dirty_repo(tmp_path: Path) -> None:
    repo_root, _ = create_phase2_repo(tmp_path)
    clean = get_workspace_status(repo_root)
    assert clean.is_git_repo is True
    assert clean.is_dirty is False

    (repo_root / "calculator.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    dirty = get_workspace_status(repo_root)
    assert dirty.is_dirty is True


def test_workspace_backup_and_apply_patch(tmp_path: Path) -> None:
    repo_root, ticket_path = create_phase2_repo(tmp_path)
    status = require_git_repo(repo_root)
    assert status.is_git_repo is True

    backup_path = create_pre_patch_backup(
        repo_root, repo_root / ".automaxfix" / "reports", "AMF-20260520-001"
    )
    assert backup_path.exists()
    artifact_path = write_patch_artifact(
        repo_root / ".automaxfix" / "logs",
        "AMF-20260520-001",
        build_fix_patch(),
        github_actions_run_url="https://github.com/example/project/actions/runs/123",
    )
    assert (
        "GitHub Actions run: https://github.com/example/project/actions/runs/123"
        in artifact_path.read_text(encoding="utf-8")
    )

    apply_patch(repo_root, build_fix_patch())
    assert "return a + b" in (repo_root / "calculator.py").read_text(encoding="utf-8")

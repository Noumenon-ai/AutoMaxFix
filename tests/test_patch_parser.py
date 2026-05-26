from __future__ import annotations

from pathlib import Path

from automaxfix.models import Config
from automaxfix.patch_parser import validate_patch_text
from tests.helpers import (
    build_fix_patch,
    build_new_source_patch,
    build_new_test_patch,
    create_phase2_repo,
)


def test_patch_parser_accepts_safe_patch(tmp_path: Path) -> None:
    repo_root, _ = create_phase2_repo(tmp_path)
    result = validate_patch_text(
        build_fix_patch(), repo_root=repo_root, config=Config()
    )
    assert result.valid is True
    assert result.files_changed == ["calculator.py"]


def test_patch_parser_blocks_sensitive_path(tmp_path: Path) -> None:
    repo_root, _ = create_phase2_repo(tmp_path)
    patch = """diff --git a/.env b/.env
--- a/.env
+++ b/.env
@@ -1 +1 @@
-A=1
+A=2
"""
    result = validate_patch_text(patch, repo_root=repo_root, config=Config())
    assert result.valid is False
    assert any(".env" in item for item in result.errors)


def test_patch_parser_allows_new_test_files(tmp_path: Path) -> None:
    repo_root, _ = create_phase2_repo(tmp_path)
    result = validate_patch_text(
        build_new_test_patch(), repo_root=repo_root, config=Config()
    )
    assert result.valid is True
    assert result.new_files == ["tests/test_repro.py"]


def test_patch_parser_blocks_new_source_files_by_default(tmp_path: Path) -> None:
    repo_root, _ = create_phase2_repo(tmp_path)
    result = validate_patch_text(
        build_new_source_patch(), repo_root=repo_root, config=Config()
    )
    assert result.valid is False
    assert any("Creating new source files is blocked" in item for item in result.errors)

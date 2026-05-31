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


def test_validate_patch_rejects_modifying_reproduction_test(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    repro_test = tests_dir / "test_repro.py"
    repro_test.write_text(
        "def test_repro():\n    assert 2 + 2 == 4\n",
        encoding="utf-8",
    )
    patch = """diff --git a/tests/test_repro.py b/tests/test_repro.py
--- a/tests/test_repro.py
+++ b/tests/test_repro.py
@@ -1,2 +1,2 @@
 def test_repro():
-    assert 2 + 2 == 4
+    assert True
"""
    result = validate_patch_text(
        patch,
        repo_root=tmp_path,
        config=Config(),
        reproduction_test="tests/test_repro.py",
    )
    assert result.valid is False
    assert any("reproduction test" in item for item in result.errors)


def test_validate_patch_allows_different_test_file(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_repro.py").write_text(
        "def test_repro():\n    assert 2 + 2 == 4\n",
        encoding="utf-8",
    )
    other_test = tests_dir / "test_other.py"
    other_test.write_text(
        "def test_other():\n    assert 1 == 1\n",
        encoding="utf-8",
    )
    patch = """diff --git a/tests/test_other.py b/tests/test_other.py
--- a/tests/test_other.py
+++ b/tests/test_other.py
@@ -1,2 +1,2 @@
 def test_other():
-    assert 1 == 1
+    assert 1 + 1 == 2
"""
    result = validate_patch_text(
        patch,
        repo_root=tmp_path,
        config=Config(),
        reproduction_test="tests/test_repro.py",
    )
    assert result.valid is True

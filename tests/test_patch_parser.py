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


def _weaken_other_test_patch() -> str:
    return """diff --git a/tests/test_other.py b/tests/test_other.py
--- a/tests/test_other.py
+++ b/tests/test_other.py
@@ -1,2 +1,2 @@
 def test_other():
-    assert expensive_check() == 42
+    assert True
"""


def _setup_two_tests(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_repro.py").write_text(
        "def test_repro():\n    assert 2 + 2 == 4\n",
        encoding="utf-8",
    )
    (tests_dir / "test_other.py").write_text(
        "def test_other():\n    assert expensive_check() == 42\n",
        encoding="utf-8",
    )


def test_validate_patch_blocks_editing_other_existing_test(tmp_path: Path) -> None:
    # A fix must not weaken a DIFFERENT existing test to pass — not just the
    # designated reproduction. (Red-team hole, 2026-05-31.)
    _setup_two_tests(tmp_path)
    result = validate_patch_text(
        _weaken_other_test_patch(),
        repo_root=tmp_path,
        config=Config(),
        reproduction_test="tests/test_repro.py",
    )
    assert result.valid is False
    assert any("existing test files" in item for item in result.errors)


def test_validate_patch_blocks_test_edit_in_no_repro_mode(tmp_path: Path) -> None:
    # The mode the UI / watchdog / loop actually use: no single reproduction is
    # attached. The patch must STILL be unable to weaken any existing test.
    _setup_two_tests(tmp_path)
    result = validate_patch_text(
        _weaken_other_test_patch(),
        repo_root=tmp_path,
        config=Config(),  # note: NO reproduction_test passed
    )
    assert result.valid is False
    assert any("existing test files" in item for item in result.errors)


def test_block_test_edits_opt_out_allows_test_edit(tmp_path: Path) -> None:
    # The escape hatch: a project that deliberately wants AMF to edit tests can
    # set block_test_edits=False.
    _setup_two_tests(tmp_path)
    cfg = Config()
    cfg.patch.block_test_edits = False
    result = validate_patch_text(
        _weaken_other_test_patch(),
        repo_root=tmp_path,
        config=cfg,
        reproduction_test="tests/test_repro.py",
    )
    assert result.valid is True


def test_is_test_path_covers_languages() -> None:
    from automaxfix.patch_parser import _is_test_path

    assert _is_test_path("tests/test_app.py")
    assert _is_test_path("pkg/handler_test.go")
    assert _is_test_path("src/foo.test.ts")
    assert _is_test_path("web/__tests__/x.jsx")
    assert _is_test_path("app/Button.spec.tsx")
    assert not _is_test_path("src/app.py")
    assert not _is_test_path("src/latest.py")

from __future__ import annotations

from pathlib import Path

from automaxfix.scanners.generic import scan

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "generic"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_generic_scanner_extracts_file_line_messages() -> None:
    records = scan(_fixture("mixed.log"), FIXTURES)
    assert len(records) == 3
    assert records[0].test_id == "src/service.py:42"
    assert records[0].file_path == "src/service.py"
    assert records[0].line == 42
    assert (
        records[0].error_summary == "AssertionError: expected cached value to refresh"
    )


def test_generic_scanner_normalizes_absolute_paths_inside_repo_root() -> None:
    repo_root = Path("/tmp/repo")
    records = scan(_fixture("absolute.log"), repo_root)
    assert len(records) == 2
    assert records[0].file_path == "src/worker.py"
    assert records[0].line == 14
    assert records[1].file_path == "tests/test_worker.py"


def test_generic_scanner_ignores_clean_logs() -> None:
    assert scan(_fixture("clean.log"), FIXTURES) == []

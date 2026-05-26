from __future__ import annotations

from pathlib import Path

from automaxfix.scanners.vitest import scan

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vitest"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_vitest_scanner_extracts_failure_blocks() -> None:
    records = scan(_fixture("failures.txt"), FIXTURES)
    assert len(records) == 2
    assert records[0].test_id == "math > adds numbers"
    assert records[0].file_path == "tests/math.test.ts"
    assert records[0].line == 7
    assert "Object.is equality" in records[0].error_summary
    assert records[1].test_id == "format > trims whitespace"


def test_vitest_scanner_handles_non_assertion_errors() -> None:
    records = scan(_fixture("hook_error.txt"), FIXTURES)
    assert len(records) == 1
    assert records[0].test_id == "setup > loads config"
    assert records[0].file_path == "tests/setup.test.ts"
    assert records[0].line == 3
    assert records[0].error_summary == "Error: missing APP_CONFIG environment variable"


def test_vitest_scanner_ignores_passing_output() -> None:
    assert scan(_fixture("passed.txt"), FIXTURES) == []

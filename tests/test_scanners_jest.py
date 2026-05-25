from __future__ import annotations

from pathlib import Path

from automaxfix.scanners.jest import scan


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "jest"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_jest_scanner_extracts_multiple_failure_sections() -> None:
    records = scan(_fixture("failures.txt"), FIXTURES)
    assert len(records) == 2
    assert records[0].test_id == "math › adds numbers"
    assert records[0].file_path == "src/math.test.js"
    assert records[0].line == 7
    assert "Object.is equality" in records[0].error_summary
    assert records[1].line == 12


def test_jest_scanner_handles_suite_failures_without_test_case_sections() -> None:
    records = scan(_fixture("suite_fail.txt"), FIXTURES)
    assert len(records) == 1
    assert records[0].test_id == "Test suite failed to run"
    assert records[0].file_path == "src/setup.test.js"
    assert records[0].line == 1
    assert "Cannot find module" in records[0].error_summary


def test_jest_scanner_ignores_passing_output() -> None:
    assert scan(_fixture("passed.txt"), FIXTURES) == []

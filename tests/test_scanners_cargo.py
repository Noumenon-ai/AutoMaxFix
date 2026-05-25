from __future__ import annotations

from pathlib import Path

from automaxfix.scanners.cargo import scan


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cargo"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_cargo_scanner_extracts_failed_tests() -> None:
    records = scan(_fixture("failures.txt"), FIXTURES)
    assert len(records) == 2
    assert records[0].test_id == "tests::adds_numbers"
    assert records[0].file_path == "src/lib.rs"
    assert records[0].line == 12
    assert records[0].error_summary == "assertion `left == right` failed"
    assert records[1].line == 24


def test_cargo_scanner_handles_stderr_failure_sections() -> None:
    records = scan(_fixture("stderr_failure.txt"), FIXTURES)
    assert len(records) == 1
    assert records[0].test_id == "tests::loads_fixture"
    assert records[0].file_path == "tests/integration.rs"
    assert records[0].line == 41
    assert records[0].error_summary == "fixture file was missing"


def test_cargo_scanner_ignores_passing_output() -> None:
    assert scan(_fixture("passed.txt"), FIXTURES) == []

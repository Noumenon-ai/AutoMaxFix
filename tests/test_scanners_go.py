from __future__ import annotations

from pathlib import Path

from automaxfix.scanners.go import scan


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "go"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_go_scanner_extracts_failed_tests() -> None:
    records = scan(_fixture("failures.txt"), FIXTURES)
    assert len(records) == 2
    assert records[0].test_id == "TestAdd"
    assert records[0].file_path == "math_test.go"
    assert records[0].line == 12
    assert records[0].error_summary == "expected 3, got 4"


def test_go_scanner_extracts_failed_subtests() -> None:
    records = scan(_fixture("subtest.txt"), FIXTURES)
    assert len(records) == 3
    assert records[0].test_id == "TestParser/missing_field"
    assert records[0].line == 27
    assert records[1].test_id == "TestParser/bad_type"
    assert records[1].line == 35
    assert records[2].test_id == "TestParser"


def test_go_scanner_ignores_passing_output() -> None:
    assert scan(_fixture("passed.txt"), FIXTURES) == []

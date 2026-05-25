from __future__ import annotations

from pathlib import Path

from automaxfix.scanners.mocha import scan


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "mocha"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_mocha_scanner_extracts_spec_failures() -> None:
    records = scan(_fixture("spec.txt"), FIXTURES)
    assert len(records) == 2
    assert records[0].test_id == "math helpers adds numbers"
    assert records[0].file_path == "test/math.spec.js"
    assert records[0].line == 7
    assert "AssertionError" in records[0].error_summary
    assert records[1].line == 12


def test_mocha_scanner_extracts_tap_failures() -> None:
    records = scan(_fixture("tap.txt"), FIXTURES)
    assert len(records) == 2
    assert records[0].test_id == "math adds numbers"
    assert records[0].file_path == "test/math.tap.js"
    assert records[0].line == 12
    assert records[0].error_summary == "expected 4 to equal 3"


def test_mocha_scanner_ignores_passing_output() -> None:
    assert scan(_fixture("passed.txt"), FIXTURES) == []

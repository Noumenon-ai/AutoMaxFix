from __future__ import annotations

from pathlib import Path

from automaxfix.scanner import parse_pytest_output, scan_pytest_output_file


def test_parse_pytest_output_extracts_failures() -> None:
    example_path = Path(__file__).resolve().parents[1] / "examples" / "broken_pytest_output.txt"
    failures = scan_pytest_output_file(example_path)
    assert len(failures) == 2
    assert failures[0].node_id == "tests/test_dupes.py::test_reminder_update_does_not_duplicate"
    assert failures[0].suspected_file == "tests/test_dupes.py"


def test_parse_pytest_output_handles_empty_text() -> None:
    assert parse_pytest_output("collected 1 item\n\n==================== 1 passed ====================\n") == []

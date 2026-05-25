from __future__ import annotations

import json
from pathlib import Path

import pytest

from automaxfix.cli import main


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_cli_scan_creates_tickets_from_jest_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    output_path = FIXTURES / "jest" / "failures.txt"
    assert main(["scan", "--jest-output", str(output_path)]) == 0
    tickets = sorted((tmp_path / ".automaxfix" / "tickets").glob("*.json"))
    assert len(tickets) == 2
    payload = json.loads(tickets[0].read_text(encoding="utf-8"))
    assert payload["source"] == "jest"


def test_cli_scan_supports_generic_format_selection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    output_path = FIXTURES / "generic" / "mixed.log"
    assert main(["scan", "--from-file", str(output_path), "--format", "generic"]) == 0
    tickets = sorted((tmp_path / ".automaxfix" / "tickets").glob("*.json"))
    assert len(tickets) == 3
    payload = json.loads(tickets[0].read_text(encoding="utf-8"))
    assert payload["source"] == "generic"


def test_cli_scan_requires_format_with_from_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    output_path = FIXTURES / "generic" / "mixed.log"
    with pytest.raises(SystemExit) as excinfo:
        main(["scan", "--from-file", str(output_path)])
    assert excinfo.value.code == 2

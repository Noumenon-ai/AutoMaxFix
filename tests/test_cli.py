from __future__ import annotations

import json
from pathlib import Path

from automaxfix.cli import main
from tests.helpers import create_phase2_repo


def test_cli_init_creates_expected_layout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert (tmp_path / ".automaxfix" / "config.yml").exists()
    assert (tmp_path / ".automaxfix" / "tickets").is_dir()
    assert (tmp_path / ".automaxfix" / "reports").is_dir()
    assert (tmp_path / ".automaxfix" / "logs").is_dir()


def test_cli_bug_creates_ticket(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    assert main(["bug", "sample bug"]) == 0
    tickets = sorted((tmp_path / ".automaxfix" / "tickets").glob("*.json"))
    assert len(tickets) == 1
    payload = json.loads(tickets[0].read_text(encoding="utf-8"))
    assert payload["title"] == "sample bug"


def test_cli_scan_creates_ticket_from_pytest_output(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    output_path = tmp_path / "failed.txt"
    output_path.write_text(
        "FAILED tests/test_example.py::test_bug - AssertionError: boom\n",
        encoding="utf-8",
    )
    assert main(["scan", "--pytest-output", str(output_path)]) == 0
    tickets = sorted((tmp_path / ".automaxfix" / "tickets").glob("*.json"))
    assert len(tickets) == 1


def test_cli_reproduce_creates_prompt_file(tmp_path: Path, monkeypatch) -> None:
    repo_root, ticket_path = create_phase2_repo(tmp_path)
    monkeypatch.chdir(repo_root)
    assert main(["reproduce", "--ticket", str(ticket_path)]) == 0
    prompts = sorted(
        (repo_root / ".automaxfix" / "logs").glob("reproduce_*.prompt.txt")
    )
    assert len(prompts) == 1
    assert "Output a unified diff only." in prompts[0].read_text(encoding="utf-8")


def test_cli_report_latest_handles_missing_reports(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    assert main(["report", "--latest"]) == 0

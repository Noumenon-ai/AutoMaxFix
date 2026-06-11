from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

from automaxfix.cli import main
from tests.helpers import create_phase2_repo


def _python_command(script: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"


def test_cli_init_creates_expected_layout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert (tmp_path / ".automaxfix" / "config.yml").exists()
    assert (tmp_path / ".automaxfix" / "tickets").is_dir()
    assert (tmp_path / ".automaxfix" / "reports").is_dir()
    assert (tmp_path / ".automaxfix" / "logs").is_dir()


def test_cli_init_creates_gitignore_with_state_dir_entry(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    assert ".automaxfix/" in gitignore.read_text(encoding="utf-8").splitlines()


def test_cli_init_appends_to_existing_gitignore_without_duplicating(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("__pycache__/\n", encoding="utf-8")

    assert main(["init"]) == 0
    lines = gitignore.read_text(encoding="utf-8").splitlines()
    assert lines == ["__pycache__/", ".automaxfix/"]

    assert main(["init"]) == 0
    lines = gitignore.read_text(encoding="utf-8").splitlines()
    assert lines.count(".automaxfix/") == 1


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


def test_cli_check_creates_ticket_with_reproduction_and_verification_command(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    config_path = tmp_path / ".automaxfix" / "config.yml"
    outside_path = (tmp_path.parent / "external-drift.txt").resolve()
    outside_path.write_text("drift\n", encoding="utf-8")
    check_command = _python_command("print('ERROR runtime drift detected')")
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n"
        + "checks:\n"
        + '  - name: "runtime drift"\n'
        + f"    command: {json.dumps(check_command)}\n"
        + '    expect: "matches"\n'
        + '    pattern: "ERROR"\n'
        + "    suspected_files:\n"
        + f"      - {json.dumps(str(outside_path))}\n",
        encoding="utf-8",
    )

    assert main(["check"]) == 0

    tickets = sorted((tmp_path / ".automaxfix" / "tickets").glob("*.json"))
    assert len(tickets) == 1
    payload = json.loads(tickets[0].read_text(encoding="utf-8"))
    assert payload["source"] == "check"
    assert payload["reproduction_command"] == check_command
    assert payload["verification_command"] == check_command
    assert "outside repo" in payload["bug_report"]
    assert "require a human" in payload["bug_report"]


def test_cli_monitor_creates_linked_regression_ticket(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    original_ticket_path = (
        tmp_path / ".automaxfix" / "tickets" / "AMF-20260601-001.json"
    )
    original_ticket_path.write_text(
        json.dumps(
            {
                "id": "AMF-20260601-001",
                "created_at": "2026-06-01T12:00:00+00:00",
                "source": "pytest",
                "title": "Fix calculator regression",
                "bug_report": "calculator test failed",
                "status": "passed",
                "suspected_files": ["calculator.py"],
                "reproduction_command": "pytest tests/test_calculator.py -v",
                "verification_command": _python_command(
                    "import sys; print('boom'); raise SystemExit(7)"
                ),
            }
        ),
        encoding="utf-8",
    )

    assert main(["monitor"]) == 0

    tickets = sorted((tmp_path / ".automaxfix" / "tickets").glob("*.json"))
    assert len(tickets) == 2

    original_payload = json.loads(original_ticket_path.read_text(encoding="utf-8"))
    regression_path = next(path for path in tickets if path != original_ticket_path)
    regression_payload = json.loads(regression_path.read_text(encoding="utf-8"))

    assert original_payload["status"] == "passed"
    assert regression_payload["source"] == "regression"
    assert regression_payload["regressed_from"] == "AMF-20260601-001"
    assert (
        regression_payload["verification_command"]
        == original_payload["verification_command"]
    )
    assert (
        regression_payload["reproduction_command"]
        == "pytest tests/test_calculator.py -v"
    )
    assert regression_payload["suspected_files"] == ["calculator.py"]
    assert "content_sha256" in regression_payload

from __future__ import annotations

import json
from pathlib import Path

from automaxfix.cli import main
from automaxfix.ticket import load_ticket, save_ticket
from tests.helpers import build_fix_patch, create_phase2_repo


def test_phase2_cli_run_manual_patch_passes(tmp_path: Path, monkeypatch) -> None:
    repo_root, ticket_path = create_phase2_repo(tmp_path)
    patch_path = tmp_path / "fix.diff"
    patch_path.write_text(build_fix_patch(), encoding="utf-8")

    monkeypatch.chdir(repo_root)
    assert (
        main(
            [
                "run",
                "--ticket",
                str(ticket_path),
                "--patch-file",
                str(patch_path),
                "--yes",
            ]
        )
        == 0
    )

    ticket = load_ticket(ticket_path)
    assert ticket.status == "passed"
    assert "return a + b" in (repo_root / "calculator.py").read_text(encoding="utf-8")

    reports = sorted((repo_root / ".automaxfix" / "reports").glob("*.md"))
    assert len(reports) == 1
    assert "Final verdict: PASS" in reports[0].read_text(encoding="utf-8")


def test_phase2_cli_run_requires_reproduction(tmp_path: Path, monkeypatch) -> None:
    repo_root, ticket_path = create_phase2_repo(tmp_path)
    patch_path = tmp_path / "fix.diff"
    patch_path.write_text(build_fix_patch(), encoding="utf-8")

    ticket = load_ticket(ticket_path)
    ticket.reproduction_test = None
    save_ticket(ticket, repo_root / ".automaxfix" / "tickets")

    monkeypatch.chdir(repo_root)
    assert (
        main(
            [
                "run",
                "--ticket",
                str(ticket_path),
                "--patch-file",
                str(patch_path),
                "--yes",
            ]
        )
        == 0
    )

    report = sorted((repo_root / ".automaxfix" / "reports").glob("*.md"))[-1]
    assert (
        "No reproduction test found. Create reproduction test before patching."
        in report.read_text(encoding="utf-8")
    )


def _attach_check_definition(
    repo_root: Path, ticket_path: Path, *, pattern: str
) -> None:
    from tests.helpers import run_checked

    log_path = repo_root / "app.log"
    log_path.write_text("service started\nERROR boom\n", encoding="utf-8")
    run_checked(["git", "add", "app.log"], cwd=repo_root)
    run_checked(["git", "commit", "-m", "add app log"], cwd=repo_root)

    ticket = load_ticket(ticket_path)
    ticket.check_definition = {
        "name": "error appeared in log",
        "command": "cat app.log",
        "expect": "matches",
        "pattern": pattern,
    }
    save_ticket(ticket, repo_root / ".automaxfix" / "tickets")


def test_phase2_cli_run_fails_when_originating_check_still_fails(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root, ticket_path = create_phase2_repo(tmp_path)
    _attach_check_definition(repo_root, ticket_path, pattern="ERROR")
    patch_path = tmp_path / "fix.diff"
    patch_path.write_text(build_fix_patch(), encoding="utf-8")

    monkeypatch.chdir(repo_root)
    assert (
        main(
            [
                "run",
                "--ticket",
                str(ticket_path),
                "--patch-file",
                str(patch_path),
                "--yes",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "Originating check 'error appeared in log' failed after patch" in output

    ticket = load_ticket(ticket_path)
    assert ticket.status == "failed"
    assert "Originating check" in (ticket.result or "")
    # Patch was rolled back because the check that filed the ticket still fails.
    assert "return a - b" in (repo_root / "calculator.py").read_text(encoding="utf-8")


def test_phase2_cli_run_passes_when_originating_check_passes(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root, ticket_path = create_phase2_repo(tmp_path)
    _attach_check_definition(repo_root, ticket_path, pattern="FATAL")
    patch_path = tmp_path / "fix.diff"
    patch_path.write_text(build_fix_patch(), encoding="utf-8")

    monkeypatch.chdir(repo_root)
    assert (
        main(
            [
                "run",
                "--ticket",
                str(ticket_path),
                "--patch-file",
                str(patch_path),
                "--yes",
            ]
        )
        == 0
    )

    ticket = load_ticket(ticket_path)
    assert ticket.status == "passed"
    assert "cat app.log" in ticket.tests_run
    assert "return a + b" in (repo_root / "calculator.py").read_text(encoding="utf-8")


def test_phase2_cli_first_run_without_yes_asks_for_approval_not_dirty(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from tests.helpers import run_checked

    repo_root, ticket_path = create_phase2_repo(tmp_path)
    # Repos that did not gitignore .automaxfix used to see AutoMaxFix's own
    # ticket and log writes as a dirty workspace on the very first run.
    (repo_root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    run_checked(["git", "add", ".gitignore"], cwd=repo_root)
    run_checked(["git", "commit", "-m", "drop state dir ignore"], cwd=repo_root)

    patch_path = tmp_path / "fix.diff"
    patch_path.write_text(build_fix_patch(), encoding="utf-8")

    monkeypatch.chdir(repo_root)
    assert (
        main(["run", "--ticket", str(ticket_path), "--patch-file", str(patch_path)])
        == 0
    )

    output = capsys.readouterr().out
    assert "Human approval required. Re-run with --yes." in output
    assert "Workspace is dirty" not in output


def test_phase2_cli_run_refuses_tampered_ticket(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo_root, ticket_path = create_phase2_repo(tmp_path)
    patch_path = tmp_path / "fix.diff"
    patch_path.write_text(build_fix_patch(), encoding="utf-8")

    payload = json.loads(ticket_path.read_text(encoding="utf-8"))
    payload["reproduction_test"] = "tests/test_other.py"
    ticket_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.chdir(repo_root)
    exit_code = main(
        [
            "run",
            "--ticket",
            str(ticket_path),
            "--patch-file",
            str(patch_path),
            "--yes",
        ]
    )

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "integrity check" in output
    assert "Refusing to load a tampered ticket" in output
    assert "return a - b" in (repo_root / "calculator.py").read_text(encoding="utf-8")

from __future__ import annotations

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

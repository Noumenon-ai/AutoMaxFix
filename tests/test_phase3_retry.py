from __future__ import annotations

from automaxfix.cli import main
from automaxfix.ticket import load_ticket
from tests.helpers import create_phase2_repo, write_repo_config


def test_phase3_cli_retries_invalid_diff_once_then_passes(
    tmp_path, monkeypatch
) -> None:
    repo_root, ticket_path = create_phase2_repo(tmp_path)
    script_path = tmp_path / "retry_agent.py"
    script_path.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "prompt = Path(sys.argv[1]).read_text(encoding='utf-8')\n"
        "if 'Previous output failed unified diff validation.' in prompt:\n"
        "    print('''diff --git a/calculator.py b/calculator.py\\n"
        "--- a/calculator.py\\n"
        "+++ b/calculator.py\\n"
        "@@ -1,2 +1,2 @@\\n"
        " def add(a, b):\\n"
        "-    return a - b\\n"
        "+    return a + b\\n''')\n"
        "else:\n"
        "    print('not a diff')\n",
        encoding="utf-8",
    )
    write_repo_config(
        repo_root,
        f"""repo_path: "."
test_command: "pytest -q"
targeted_test_command: "pytest {{test_file}} -v"
tickets_dir: ".automaxfix/tickets"
reports_dir: ".automaxfix/reports"
allowed_paths:
  - "."
blocked_paths:
  - ".git"
  - ".venv"
  - "node_modules"
  - "__pycache__"
require_reproduction_test: true
agent:
  mode: "codex_cli"
  command: "python3 {script_path} {{prompt_file}}"
  timeout_seconds: 900
patch:
  require_unified_diff: true
  max_patch_attempts: 3
  max_files_changed: 8
  allow_new_tests: true
  allow_new_source_files: false
approval:
  require_human_approval: true
""",
    )

    monkeypatch.chdir(repo_root)
    assert (
        main(["run", "--ticket", str(ticket_path), "--agent", "codex_cli", "--yes"])
        == 0
    )

    ticket = load_ticket(ticket_path)
    assert ticket.status == "passed"
    report = sorted((repo_root / ".automaxfix" / "reports").glob("*.md"))[-1].read_text(
        encoding="utf-8"
    )
    assert "Invalid diff retries: 1" in report
    assert "Attempt count: 2" in report
    assert "Final verdict: PASS" in report


def test_phase3_cli_does_not_retry_unsafe_diff(tmp_path, monkeypatch) -> None:
    repo_root, ticket_path = create_phase2_repo(tmp_path)
    script_path = tmp_path / "unsafe_agent.py"
    script_path.write_text(
        "print('''diff --git a/.env b/.env\\n"
        "--- a/.env\\n"
        "+++ b/.env\\n"
        "@@ -1 +1 @@\\n"
        "-A=1\\n"
        "+A=2\\n''')\n",
        encoding="utf-8",
    )
    write_repo_config(
        repo_root,
        f"""repo_path: "."
test_command: "pytest -q"
targeted_test_command: "pytest {{test_file}} -v"
tickets_dir: ".automaxfix/tickets"
reports_dir: ".automaxfix/reports"
allowed_paths:
  - "."
blocked_paths:
  - ".git"
  - ".venv"
  - "node_modules"
  - "__pycache__"
require_reproduction_test: true
agent:
  mode: "codex_cli"
  command: "python3 {script_path} {{prompt_file}}"
  timeout_seconds: 900
patch:
  require_unified_diff: true
  max_patch_attempts: 3
  max_files_changed: 8
  allow_new_tests: true
  allow_new_source_files: false
approval:
  require_human_approval: true
""",
    )

    monkeypatch.chdir(repo_root)
    assert (
        main(["run", "--ticket", str(ticket_path), "--agent", "codex_cli", "--yes"])
        == 0
    )

    ticket = load_ticket(ticket_path)
    assert ticket.status == "failed"
    report = sorted((repo_root / ".automaxfix" / "reports").glob("*.md"))[-1].read_text(
        encoding="utf-8"
    )
    assert "Invalid diff retries: 0" in report
    assert "Attempt count: 1" in report
    assert "Editing .env is blocked" in report

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from automaxfix.agent_runner import load_patch_from_file, run_agent_patch
from automaxfix.models import AgentConfig, Config
from automaxfix.patcher import inspect_repo
from automaxfix.ticket import load_ticket
from automaxfix.utils import run_command
from tests.helpers import build_fix_patch, create_phase2_repo


def test_manual_patch_file_mode_loads_diff(tmp_path: Path) -> None:
    patch_path = tmp_path / "patch.diff"
    patch_path.write_text(build_fix_patch(), encoding="utf-8")
    result = load_patch_from_file(patch_path)
    assert result.mode == "manual_patch_file"
    assert "diff --git a/calculator.py b/calculator.py" in result.patch_text


@pytest.mark.parametrize("mode", ["codex_cli", "claude_cli"])
def test_agent_runner_executes_external_cli_and_reads_prompt(
    tmp_path: Path, mode: str
) -> None:
    repo_root, ticket_path = create_phase2_repo(tmp_path)
    ticket = load_ticket(ticket_path)
    repo_context = inspect_repo(ticket, repo_root)
    script_path = tmp_path / "fake_agent.py"
    script_path.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "prompt = Path(sys.argv[1]).read_text(encoding='utf-8')\n"
        "assert 'AutoMaxFix Ticket Repair Attempt 1' in prompt\n"
        "print('''diff --git a/calculator.py b/calculator.py\\n"
        "--- a/calculator.py\\n"
        "+++ b/calculator.py\\n"
        "@@ -1,2 +1,2 @@\\n"
        " def add(a, b):\\n"
        "-    return a - b\\n"
        "+    return a + b\\n''')\n",
        encoding="utf-8",
    )
    config = Config(
        agent=AgentConfig(mode=mode, command=f"python3 {script_path} {{prompt_file}}")
    )

    result = run_agent_patch(
        mode=mode,
        repo_root=repo_root,
        logs_dir=repo_root / ".automaxfix" / "logs",
        config=config,
        ticket=ticket,
        repo_context=repo_context,
    )

    assert result.mode == mode
    assert "diff --git a/calculator.py b/calculator.py" in result.stdout
    assert result.prompt_file is not None
    assert result.prompt_file.exists()
    assert result.output_file is not None
    assert result.output_file.exists()


def test_run_command_allow_full_env_controls_secret_visibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "sk-zzzzzzzzzzzzzzzzzzzz"
    monkeypatch.setenv("AMF_TEST_SECRET", secret)
    command = [
        sys.executable,
        "-c",
        "import os; print(os.environ.get('AMF_TEST_SECRET', ''))",
    ]

    restricted = run_command(command, cwd=tmp_path, allow_full_env=False)
    allowed = run_command(command, cwd=tmp_path, allow_full_env=True)

    assert "sk-zzz" not in restricted.stdout
    assert "sk-zzz" in allowed.stdout


def test_agent_runner_sanitizes_persisted_agent_log(tmp_path: Path) -> None:
    repo_root, ticket_path = create_phase2_repo(tmp_path)
    ticket = load_ticket(ticket_path)
    repo_context = inspect_repo(ticket, repo_root)
    secret = "sk-abcdefghijklmnopqrstuvwx"
    script_path = tmp_path / "fake_agent_secret.py"
    script_path.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "prompt = Path(sys.argv[1]).read_text(encoding='utf-8')\n"
        "assert 'AutoMaxFix Ticket Repair Attempt 1' in prompt\n"
        "print('''diff --git a/calculator.py b/calculator.py\\n"
        "--- a/calculator.py\\n"
        "+++ b/calculator.py\\n"
        "@@ -1,2 +1,2 @@\\n"
        " def add(a, b):\\n"
        f'-    return "{secret}"\\n'
        "+    return a + b\\n''')\n",
        encoding="utf-8",
    )
    config = Config(
        agent=AgentConfig(
            mode="codex_cli",
            command=f"python3 {script_path} {{prompt_file}}",
        )
    )

    result = run_agent_patch(
        mode="codex_cli",
        repo_root=repo_root,
        logs_dir=repo_root / ".automaxfix" / "logs",
        config=config,
        ticket=ticket,
        repo_context=repo_context,
    )

    assert result.output_file is not None
    persisted = result.output_file.read_text(encoding="utf-8")
    assert secret in result.stdout
    assert secret not in persisted
    assert "[REDACTED]" in persisted

from __future__ import annotations

from pathlib import Path

from automaxfix.models import AgentAttempt, CommandResult, Config, Ticket
from automaxfix.reporter import latest_report_path, write_report


def test_write_report_and_fetch_latest(tmp_path: Path) -> None:
    config = Config()
    ticket = Ticket(
        id="AMF-20260520-001",
        created_at="2026-05-20T00:00:00+00:00",
        source="user",
        title="Example bug",
        bug_report="Example bug",
        github_actions_run_url="https://github.com/example/project/actions/runs/123",
        status="failed",
    )
    targeted = CommandResult(
        command="pytest tests/test_example.py -v",
        returncode=1,
        stdout="assert 1 == 2",
        stderr="",
        duration_seconds=0.123,
    )
    report_path = write_report(
        repo_root=tmp_path,
        config=config,
        ticket=ticket,
        agent_used="manual_patch_file",
        attempt_count=2,
        invalid_diff_retries=1,
        reproduction_before_patch="Failed as expected.",
        final_diff_validation="passed; validated unified diff touching 1 file.",
        safety_gates="reproduction=passed; diff_validation=passed; workspace=passed; approval=passed; patch_apply=not run",
        files_changed=["calculator.py"],
        approval="Approved by operator.",
        attempts=[
            AgentAttempt(
                attempt_number=1,
                mode="codex_cli",
                agent_used="codex_cli",
                is_valid_diff=False,
                validation_errors=["Patch is not a unified diff."],
                retryable_invalid_diff=True,
            ),
            AgentAttempt(
                attempt_number=2,
                mode="codex_cli",
                agent_used="codex_cli",
                is_valid_diff=True,
            ),
        ],
        targeted_test=targeted,
        regression_test=None,
        final_verdict="FAIL",
        rollback_instructions="No patch was applied.",
        next_step="Attach the report to a coding agent.",
    )
    assert report_path.exists()
    latest = latest_report_path(tmp_path, config)
    assert latest == report_path
    contents = report_path.read_text(encoding="utf-8")
    assert "AutoMaxFix Phase 3 Report" in contents
    assert "Agent used: manual_patch_file" in contents
    assert "Attempt count: 2" in contents
    assert "GitHub Actions run: https://github.com/example/project/actions/runs/123" in contents

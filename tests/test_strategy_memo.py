from __future__ import annotations

from pathlib import Path

from automaxfix.cli import main
from automaxfix.models import (
    AgentAttempt,
    CommandResult,
    StrategyName,
    TicketStrategyAttempt,
)
from automaxfix.ticket import create_bug_ticket, load_ticket, save_ticket
from tests.helpers import build_fix_patch, create_phase2_repo


def _install_retry_stubs(monkeypatch):
    strategies_seen: list[StrategyName] = []

    def fake_run_agent_patch(
        *,
        mode: str,
        repo_root: Path,
        logs_dir: Path,
        config,
        ticket,
        repo_context,
        command_override=None,
        strategy: StrategyName,
        attempt_number: int = 1,
        validation_errors=None,
    ) -> AgentAttempt:
        del (
            repo_root,
            logs_dir,
            config,
            ticket,
            repo_context,
            command_override,
            validation_errors,
        )
        strategies_seen.append(strategy)
        return AgentAttempt(
            attempt_number=attempt_number,
            mode=mode,
            agent_used=mode,
            strategy=strategy,
            stdout=build_fix_patch(),
            duration_seconds=0.01,
        )

    def fake_run_targeted_test(
        config, repo_root: Path, test_file: str
    ) -> CommandResult:
        del config
        fixed = "return a + b" in (repo_root / "calculator.py").read_text(
            encoding="utf-8"
        )
        return CommandResult(
            command=f"pytest {test_file} -v",
            returncode=0 if fixed else 1,
            stdout="targeted passed" if fixed else "targeted failed",
            stderr="",
            duration_seconds=0.01,
        )

    def fake_run_regression_suite(config, repo_root: Path) -> CommandResult:
        del config, repo_root
        return CommandResult(
            command="pytest -q",
            returncode=1,
            stdout="persistent regression failure",
            stderr="",
            duration_seconds=0.01,
        )

    monkeypatch.setattr("automaxfix.cli.run_agent_patch", fake_run_agent_patch)
    monkeypatch.setattr("automaxfix.cli.run_targeted_test", fake_run_targeted_test)
    monkeypatch.setattr(
        "automaxfix.cli.run_regression_suite", fake_run_regression_suite
    )
    return strategies_seen


def test_ticket_strategy_memo_round_trips_through_save_and_load(tmp_path: Path) -> None:
    ticket, path = create_bug_ticket("memo round trip", tmp_path)
    ticket.strategy_memo.attempts.append(
        TicketStrategyAttempt(
            strategy=StrategyName.REFACTOR,
            reason="regression failed",
            agent_used="codex_cli",
            duration_sec=1.25,
            succeeded=False,
        )
    )
    save_ticket(ticket, tmp_path)

    reloaded = load_ticket(path)
    assert len(reloaded.strategy_memo.attempts) == 1
    assert reloaded.strategy_memo.attempts[0].strategy == StrategyName.REFACTOR
    assert reloaded.strategy_memo.attempts[0].reason == "regression failed"


def test_strategy_memo_persists_across_reruns(tmp_path: Path, monkeypatch) -> None:
    repo_root, ticket_path = create_phase2_repo(tmp_path)
    strategies_seen = _install_retry_stubs(monkeypatch)

    monkeypatch.chdir(repo_root)
    assert (
        main(
            [
                "run",
                "--ticket",
                str(ticket_path),
                "--agent",
                "codex_cli",
                "--max-attempts",
                "1",
                "--yes",
            ]
        )
        == 0
    )
    first_run = load_ticket(ticket_path)
    assert [item.strategy for item in first_run.strategy_memo.attempts] == [
        StrategyName.MINIMAL
    ]

    assert (
        main(
            [
                "run",
                "--ticket",
                str(ticket_path),
                "--agent",
                "codex_cli",
                "--max-attempts",
                "1",
                "--yes",
            ]
        )
        == 0
    )

    reloaded = load_ticket(ticket_path)
    assert strategies_seen == [StrategyName.MINIMAL, StrategyName.TEST_FIRST]
    assert [item.strategy for item in reloaded.strategy_memo.attempts] == [
        StrategyName.MINIMAL,
        StrategyName.TEST_FIRST,
    ]

from __future__ import annotations

from pathlib import Path

from automaxfix.cli import _build_parser, main
from automaxfix.models import AgentAttempt, CommandResult, StrategyName
from automaxfix.ticket import load_ticket
from tests.helpers import build_fix_patch, create_phase2_repo


def _install_attempt_stubs(monkeypatch, regression_results: list[tuple[bool, str]]):
    strategies_seen: list[StrategyName] = []
    regression_index = {"value": 0}

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
        index = min(regression_index["value"], len(regression_results) - 1)
        passed, message = regression_results[index]
        regression_index["value"] += 1
        return CommandResult(
            command="pytest -q",
            returncode=0 if passed else 1,
            stdout=message,
            stderr="",
            duration_seconds=0.01,
        )

    monkeypatch.setattr("automaxfix.cli.run_agent_patch", fake_run_agent_patch)
    monkeypatch.setattr("automaxfix.cli.run_targeted_test", fake_run_targeted_test)
    monkeypatch.setattr(
        "automaxfix.cli.run_regression_suite", fake_run_regression_suite
    )
    return strategies_seen


def test_run_parser_defaults_max_attempts_to_three() -> None:
    args = _build_parser().parse_args(["run", "--ticket", "ticket.json"])
    assert args.max_attempts == 3


def test_each_attempt_picks_a_different_strategy(tmp_path: Path, monkeypatch) -> None:
    repo_root, ticket_path = create_phase2_repo(tmp_path)
    strategies_seen = _install_attempt_stubs(
        monkeypatch,
        [
            (False, "regression attempt 1 failed"),
            (False, "regression attempt 2 failed"),
            (False, "regression attempt 3 failed"),
        ],
    )

    monkeypatch.chdir(repo_root)
    assert (
        main(["run", "--ticket", str(ticket_path), "--agent", "codex_cli", "--yes"])
        == 0
    )

    ticket = load_ticket(ticket_path)
    assert strategies_seen == [
        StrategyName.MINIMAL,
        StrategyName.TEST_FIRST,
        StrategyName.REFACTOR,
    ]
    assert [item.strategy for item in ticket.strategy_memo.attempts] == strategies_seen


def test_pass_on_attempt_two_stops_at_attempt_two(tmp_path: Path, monkeypatch) -> None:
    repo_root, ticket_path = create_phase2_repo(tmp_path)
    strategies_seen = _install_attempt_stubs(
        monkeypatch,
        [
            (False, "regression attempt 1 failed"),
            (True, "regression passed"),
            (False, "regression attempt 3 failed"),
        ],
    )

    monkeypatch.chdir(repo_root)
    assert (
        main(
            [
                "run",
                "--ticket",
                str(ticket_path),
                "--agent",
                "codex_cli",
                "--yes",
            ]
        )
        == 0
    )

    ticket = load_ticket(ticket_path)
    assert ticket.status == "passed"
    assert strategies_seen == [StrategyName.MINIMAL, StrategyName.TEST_FIRST]
    assert len(ticket.strategy_memo.attempts) == 2
    assert ticket.strategy_memo.attempts[-1].succeeded is True


def test_all_failed_scenario_reports_the_last_failure(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root, ticket_path = create_phase2_repo(tmp_path)
    strategies_seen = _install_attempt_stubs(
        monkeypatch,
        [
            (False, "regression attempt 1 failed"),
            (False, "regression attempt 2 failed"),
            (False, "regression attempt 3 failed"),
        ],
    )

    monkeypatch.chdir(repo_root)
    assert (
        main(["run", "--ticket", str(ticket_path), "--agent", "codex_cli", "--yes"])
        == 0
    )

    ticket = load_ticket(ticket_path)
    assert strategies_seen == [
        StrategyName.MINIMAL,
        StrategyName.TEST_FIRST,
        StrategyName.REFACTOR,
    ]
    assert (
        ticket.result
        == "Regression suite failed after patch: regression attempt 3 failed"
    )
    assert ticket.strategy_memo.attempts[-1].reason == ticket.result


def test_max_attempts_one_matches_single_strategy_behavior(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root, ticket_path = create_phase2_repo(tmp_path)
    strategies_seen = _install_attempt_stubs(
        monkeypatch,
        [(False, "regression attempt 1 failed")],
    )

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

    ticket = load_ticket(ticket_path)
    assert ticket.status == "failed"
    assert strategies_seen == [StrategyName.MINIMAL]
    assert len(ticket.strategy_memo.attempts) == 1

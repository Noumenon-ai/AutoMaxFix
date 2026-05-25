from __future__ import annotations

import io
import runpy
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock

from automaxfix.models import Config, PatchValidationResult, WatchConfig
from automaxfix.scanners import SCANNERS
from automaxfix.ticket import create_ticket_from_failures, load_ticket, resolve_tickets_dir
from automaxfix.watcher import WatchRuntime, watch_loop


class FakeClock:
    def __init__(self) -> None:
        self.current = 0.0
        self.sleeps: list[float] = []
        self.on_sleep = None

    def time(self) -> float:
        return self.current

    def monotonic(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += seconds
        if self.on_sleep is not None:
            self.on_sleep(seconds)


class FakeSignalModule:
    SIGINT = 2

    def __init__(self) -> None:
        self.handlers: dict[int, object] = {}

    def signal(self, signum: int, handler: object) -> object | None:
        previous = self.handlers.get(signum)
        self.handlers[signum] = handler
        return previous

    def emit_sigint(self) -> None:
        handler = self.handlers.get(self.SIGINT)
        if callable(handler):
            handler(self.SIGINT, None)


def _create_repo_root(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    tests_dir = repo_root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text(
        "def test_bug():\n    assert False\n",
        encoding="utf-8",
    )
    return repo_root


def _write_fake_runner_script(
    tmp_path: Path,
    *,
    scenarios: list[tuple[int, str]],
) -> tuple[Path, Path, str]:
    script_path = tmp_path / "fake_runner.py"
    state_path = tmp_path / "runner_state.txt"
    script_path.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        f"SCENARIOS = {scenarios!r}\n"
        "state_path = Path(sys.argv[1])\n"
        "count = int(state_path.read_text(encoding='utf-8')) if state_path.exists() else 0\n"
        "state_path.write_text(str(count + 1), encoding='utf-8')\n"
        "index = count if count < len(SCENARIOS) else len(SCENARIOS) - 1\n"
        "exit_code, output = SCENARIOS[index]\n"
        "print(output, end='')\n"
        "raise SystemExit(exit_code)\n",
        encoding="utf-8",
    )
    return script_path, state_path, f"python3 {script_path} {state_path}"


def _build_inprocess_subprocess_run() -> Mock:
    def run_inprocess(argv, **kwargs):
        del kwargs
        buffer = io.StringIO()
        saved_argv = sys.argv
        sys.argv = list(argv[1:])
        returncode = 0
        try:
            with redirect_stdout(buffer), redirect_stderr(buffer):
                try:
                    runpy.run_path(argv[1], run_name="__main__")
                except SystemExit as exc:
                    returncode = int(exc.code or 0)
        finally:
            sys.argv = saved_argv
        return subprocess.CompletedProcess(argv, returncode, buffer.getvalue())

    return Mock(side_effect=run_inprocess)


def _build_scan_failures(repo_root: Path, config: Config, test_runner: str):
    def scan_failures(output_text: str):
        failures = SCANNERS[test_runner](output_text, repo_root)
        return create_ticket_from_failures(
            failures,
            resolve_tickets_dir(repo_root, config),
            test_runner,
        )

    return scan_failures


def _build_runtime(
    *,
    output: io.StringIO,
    subprocess_run: Mock,
    clock: FakeClock,
    signal_module: FakeSignalModule,
    input_fn=None,
) -> WatchRuntime:
    if input_fn is None:
        input_fn = Mock(return_value="n")
    return WatchRuntime(
        subprocess_run=subprocess_run,
        input_fn=input_fn,
        sleep_fn=clock.sleep,
        now_fn=clock.time,
        monotonic_fn=clock.monotonic,
        signal_module=signal_module,
        output=output,
    )


def test_watch_starts_and_stops_cleanly_on_simulated_sigint(tmp_path: Path) -> None:
    repo_root = _create_repo_root(tmp_path)
    _, _, command = _write_fake_runner_script(tmp_path, scenarios=[(0, "1 passed\n")])
    output = io.StringIO()
    subprocess_run = _build_inprocess_subprocess_run()
    clock = FakeClock()
    signal_module = FakeSignalModule()
    clock.on_sleep = lambda seconds: signal_module.emit_sigint()

    summary = watch_loop(
        repo_root=repo_root,
        config=Config(),
        test_runner="pytest",
        command=command,
        interval=5,
        scan_failures=lambda output_text: [],
        run_ticket=lambda ticket_path, approval_callback: 0,
        runtime=_build_runtime(
            output=output,
            subprocess_run=subprocess_run,
            clock=clock,
            signal_module=signal_module,
        ),
    )

    assert summary.polls == 1
    assert summary.passes == 1
    assert summary.failures == 0
    assert "[watch] summary:" in output.getvalue()
    assert "last status: PASS" in output.getvalue()


def test_watch_polling_interval_is_respected(tmp_path: Path) -> None:
    repo_root = _create_repo_root(tmp_path)
    _, _, command = _write_fake_runner_script(
        tmp_path,
        scenarios=[(0, "1 passed\n"), (0, "1 passed\n")],
    )
    output = io.StringIO()
    subprocess_run = _build_inprocess_subprocess_run()
    clock = FakeClock()
    signal_module = FakeSignalModule()

    def stop_after_second_sleep(seconds: float) -> None:
        del seconds
        if len(clock.sleeps) == 2:
            signal_module.emit_sigint()

    clock.on_sleep = stop_after_second_sleep

    summary = watch_loop(
        repo_root=repo_root,
        config=Config(),
        test_runner="pytest",
        command=command,
        interval=7,
        scan_failures=lambda output_text: [],
        run_ticket=lambda ticket_path, approval_callback: 0,
        runtime=_build_runtime(
            output=output,
            subprocess_run=subprocess_run,
            clock=clock,
            signal_module=signal_module,
        ),
    )

    assert summary.polls == 2
    assert clock.sleeps == [7, 7]


def test_watch_failure_creates_ticket_from_scan(tmp_path: Path) -> None:
    repo_root = _create_repo_root(tmp_path)
    _, _, command = _write_fake_runner_script(
        tmp_path,
        scenarios=[(1, "FAILED tests/test_sample.py::test_bug - AssertionError: boom\n")],
    )
    output = io.StringIO()
    subprocess_run = _build_inprocess_subprocess_run()
    clock = FakeClock()
    signal_module = FakeSignalModule()
    clock.on_sleep = lambda seconds: signal_module.emit_sigint()
    config = Config()
    run_ticket = Mock(return_value=0)

    summary = watch_loop(
        repo_root=repo_root,
        config=config,
        test_runner="pytest",
        command=command,
        interval=3,
        scan_failures=_build_scan_failures(repo_root, config, "pytest"),
        run_ticket=run_ticket,
        runtime=_build_runtime(
            output=output,
            subprocess_run=subprocess_run,
            clock=clock,
            signal_module=signal_module,
        ),
    )

    tickets = sorted(resolve_tickets_dir(repo_root, config).glob("*.json"))
    assert summary.failures == 1
    assert summary.tickets_created == 1
    assert summary.patch_runs == 1
    assert len(tickets) == 1
    assert load_ticket(tickets[0]).title == "Fix failing test tests/test_sample.py::test_bug"
    run_ticket.assert_called_once()


def test_watch_pass_after_fail_does_not_trigger_second_patch_run(tmp_path: Path) -> None:
    repo_root = _create_repo_root(tmp_path)
    _, _, command = _write_fake_runner_script(
        tmp_path,
        scenarios=[
            (1, "FAILED tests/test_sample.py::test_bug - AssertionError: boom\n"),
            (0, "1 passed\n"),
        ],
    )
    output = io.StringIO()
    subprocess_run = _build_inprocess_subprocess_run()
    clock = FakeClock()
    signal_module = FakeSignalModule()

    def stop_after_second_sleep(seconds: float) -> None:
        del seconds
        if len(clock.sleeps) == 2:
            signal_module.emit_sigint()

    clock.on_sleep = stop_after_second_sleep
    config = Config()
    run_ticket = Mock(return_value=0)

    summary = watch_loop(
        repo_root=repo_root,
        config=config,
        test_runner="pytest",
        command=command,
        interval=2,
        scan_failures=_build_scan_failures(repo_root, config, "pytest"),
        run_ticket=run_ticket,
        runtime=_build_runtime(
            output=output,
            subprocess_run=subprocess_run,
            clock=clock,
            signal_module=signal_module,
        ),
    )

    assert summary.failures == 1
    assert summary.passes == 1
    assert summary.patch_runs == 1
    run_ticket.assert_called_once()


def test_watch_prompts_for_approval_by_default(tmp_path: Path) -> None:
    repo_root = _create_repo_root(tmp_path)
    _, _, command = _write_fake_runner_script(
        tmp_path,
        scenarios=[(1, "FAILED tests/test_sample.py::test_bug - AssertionError: boom\n")],
    )
    output = io.StringIO()
    subprocess_run = _build_inprocess_subprocess_run()
    clock = FakeClock()
    signal_module = FakeSignalModule()
    clock.on_sleep = lambda seconds: signal_module.emit_sigint()
    config = Config()
    input_fn = Mock(return_value="n")

    def run_ticket(ticket_path: Path, approval_callback) -> int:
        ticket = load_ticket(ticket_path)
        decision = approval_callback(
            config=config,
            ticket=ticket,
            patch_text="diff --git a/sample.py b/sample.py\n--- a/sample.py\n+++ b/sample.py\n",
            validation=PatchValidationResult(valid=True, files_changed=["sample.py"]),
            workspace=None,
        )
        assert decision.approved is False
        return 0

    summary = watch_loop(
        repo_root=repo_root,
        config=config,
        test_runner="pytest",
        command=command,
        interval=4,
        scan_failures=_build_scan_failures(repo_root, config, "pytest"),
        run_ticket=run_ticket,
        runtime=_build_runtime(
            output=output,
            subprocess_run=subprocess_run,
            clock=clock,
            signal_module=signal_module,
            input_fn=input_fn,
        ),
    )

    assert summary.approvals_granted == 0
    assert summary.approvals_denied == 1
    input_fn.assert_called_once()
    assert "diff --git a/sample.py b/sample.py" in output.getvalue()


def test_watch_autoapprove_skips_prompt_when_enabled(tmp_path: Path) -> None:
    repo_root = _create_repo_root(tmp_path)
    _, _, command = _write_fake_runner_script(
        tmp_path,
        scenarios=[(1, "FAILED tests/test_sample.py::test_bug - AssertionError: boom\n")],
    )
    output = io.StringIO()
    subprocess_run = _build_inprocess_subprocess_run()
    clock = FakeClock()
    signal_module = FakeSignalModule()
    clock.on_sleep = lambda seconds: signal_module.emit_sigint()
    config = Config(watch_mode=WatchConfig(auto_approve_in_watch=True))
    input_fn = Mock(side_effect=AssertionError("input should not be called"))

    def run_ticket(ticket_path: Path, approval_callback) -> int:
        ticket = load_ticket(ticket_path)
        decision = approval_callback(
            config=config,
            ticket=ticket,
            patch_text="diff --git a/sample.py b/sample.py\n--- a/sample.py\n+++ b/sample.py\n",
            validation=PatchValidationResult(valid=True, files_changed=["sample.py"]),
            workspace=None,
        )
        assert decision.approved is True
        return 0

    summary = watch_loop(
        repo_root=repo_root,
        config=config,
        test_runner="pytest",
        command=command,
        interval=4,
        scan_failures=_build_scan_failures(repo_root, config, "pytest"),
        run_ticket=run_ticket,
        runtime=_build_runtime(
            output=output,
            subprocess_run=subprocess_run,
            clock=clock,
            signal_module=signal_module,
            input_fn=input_fn,
        ),
    )

    assert summary.approvals_granted == 1
    assert summary.approvals_denied == 0
    assert "auto-approve enabled" in output.getvalue()

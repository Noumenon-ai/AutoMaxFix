from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest

from automaxfix.checks import CheckDefinition, run_checks
from automaxfix.config import ConfigError, parse_config_text, render_default_config
from automaxfix.models import Config


def _python_command(script: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"


def test_run_checks_exit_zero_passing_command_returns_no_failures(
    tmp_path: Path,
) -> None:
    failures = run_checks(
        [
            CheckDefinition(
                name="service up",
                command=_python_command("print('ok')"),
            )
        ],
        tmp_path,
    )

    assert failures == []


def test_run_checks_exit_zero_failure_creates_failure_record(tmp_path: Path) -> None:
    failures = run_checks(
        [
            CheckDefinition(
                name="service up",
                command=_python_command(
                    "import sys; print('boom'); print('trace', file=sys.stderr); raise SystemExit(3)"
                ),
                suspected_files=["services/app.py", "services/worker.py"],
            )
        ],
        tmp_path,
    )

    assert len(failures) == 1
    failure = failures[0]
    assert failure.test_id == "service up"
    assert failure.error_summary == "exit 3"
    assert "boom" in failure.raw_excerpt
    assert "trace" in failure.raw_excerpt
    assert failure.file_path == "services/app.py"
    assert failure.line is None


def test_run_checks_matches_pattern_present_fails(tmp_path: Path) -> None:
    failures = run_checks(
        [
            CheckDefinition(
                name="error log",
                command=_python_command("print('ERROR: runtime drift detected')"),
                expect="matches",
                pattern="ERROR",
            )
        ],
        tmp_path,
    )

    assert len(failures) == 1
    assert failures[0].error_summary == "matched /ERROR/"


def test_run_checks_matches_pattern_absent_passes(tmp_path: Path) -> None:
    failures = run_checks(
        [
            CheckDefinition(
                name="error log",
                command=_python_command("print('all clear')"),
                expect="matches",
                pattern="ERROR",
            )
        ],
        tmp_path,
    )

    assert failures == []


def test_run_checks_not_matches_pattern_absent_fails(tmp_path: Path) -> None:
    failures = run_checks(
        [
            CheckDefinition(
                name="health marker",
                command=_python_command("print('warming up')"),
                expect="not_matches",
                pattern="HEALTHY",
            )
        ],
        tmp_path,
    )

    assert len(failures) == 1
    assert failures[0].error_summary == "missing /HEALTHY/"


def test_run_checks_not_matches_pattern_present_passes(tmp_path: Path) -> None:
    failures = run_checks(
        [
            CheckDefinition(
                name="health marker",
                command=_python_command("print('HEALTHY')"),
                expect="not_matches",
                pattern="HEALTHY",
            )
        ],
        tmp_path,
    )

    assert failures == []


def test_run_checks_captures_and_truncates_output(tmp_path: Path) -> None:
    payload = json.dumps("A" * 2500)
    failures = run_checks(
        [
            CheckDefinition(
                name="noisy failure",
                command=_python_command(
                    f"import sys; print({payload}); print({payload}, file=sys.stderr); raise SystemExit(4)"
                ),
            )
        ],
        tmp_path,
    )

    assert len(failures) == 1
    assert len(failures[0].raw_excerpt) <= 2000
    assert "[truncated]" in failures[0].raw_excerpt
    assert "A" * 100 in failures[0].raw_excerpt


def test_run_checks_timeout_returns_failure(tmp_path: Path) -> None:
    failures = run_checks(
        [
            CheckDefinition(
                name="slow healthcheck",
                command=_python_command("import time; time.sleep(2)"),
                timeout_seconds=1,
            )
        ],
        tmp_path,
    )

    assert len(failures) == 1
    assert failures[0].error_summary == "timeout after 1s"


@pytest.mark.parametrize("expectation", ["matches", "not_matches"])
def test_parse_config_rejects_missing_pattern_for_pattern_checks(
    expectation: str,
) -> None:
    with pytest.raises(ConfigError, match="pattern"):
        parse_config_text(f"""
repo_path: "."
checks:
  - name: "runtime drift"
    command: "echo ready"
    expect: "{expectation}"
""")


def test_run_checks_uses_sanitized_minimal_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AMF_TEST_SECRET", "sk-zzzzzzzzzz")
    failures = run_checks(
        [
            CheckDefinition(
                name="env scrubbed",
                command=_python_command(
                    "import os, sys; secret = os.environ.get('AMF_TEST_SECRET', ''); print(secret); raise SystemExit(0 if not secret else 9)"
                ),
            )
        ],
        tmp_path,
    )

    assert failures == []


def test_config_checks_round_trip_through_to_dict_and_from_dict() -> None:
    config = parse_config_text("""
repo_path: "."
checks:
  - name: "runtime drift"
    command: "echo HEALTHY"
    expect: "not_matches"
    pattern: "HEALTHY"
    suspected_files:
      - "services/api.py"
    severity: 3
    timeout_seconds: 9
""")

    assert len(config.checks) == 1
    check = config.checks[0]
    assert check.name == "runtime drift"
    assert check.command == "echo HEALTHY"
    assert check.expect == "not_matches"
    assert check.pattern == "HEALTHY"
    assert check.suspected_files == ["services/api.py"]
    assert check.severity == 3
    assert check.timeout_seconds == 9

    reloaded = Config.from_dict(config.to_dict())
    assert reloaded.checks == config.checks


def test_render_default_config_includes_commented_check_example() -> None:
    template = render_default_config()

    assert "# checks:" in template
    assert "#   - name: " in template

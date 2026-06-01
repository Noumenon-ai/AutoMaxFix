from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import CommandResult, FailureRecord
from .utils import run_command

_OUTPUT_LIMIT = 2000
_TRUNCATION_MARKER = "\n...[truncated]"
_VALID_EXPECTATIONS = frozenset({"exit_zero", "matches", "not_matches"})


@dataclass(slots=True)
class CheckDefinition:
    name: str
    command: str
    expect: str = "exit_zero"
    pattern: str | None = None
    suspected_files: list[str] = field(default_factory=list)
    severity: int = 2
    timeout_seconds: int = 60

    def __post_init__(self) -> None:
        self.name = str(self.name).strip()
        self.command = str(self.command).strip()
        self.expect = str(self.expect).strip()
        self.pattern = str(self.pattern) if self.pattern is not None else None
        self.suspected_files = [str(item) for item in self.suspected_files]
        self.severity = int(self.severity)
        self.timeout_seconds = int(self.timeout_seconds)

        if not self.name:
            raise ValueError("Check definition requires a non-empty name")
        if not self.command:
            raise ValueError(f"Check {self.name!r} requires a non-empty command")
        if self.expect not in _VALID_EXPECTATIONS:
            allowed = ", ".join(sorted(_VALID_EXPECTATIONS))
            raise ValueError(
                f"Check {self.name!r} has unsupported expect={self.expect!r}; expected one of {allowed}"
            )
        if self.expect in {"matches", "not_matches"} and not self.pattern:
            raise ValueError(
                f"Check {self.name!r} requires pattern when expect={self.expect!r}"
            )
        if self.pattern is not None:
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise ValueError(
                    f"Check {self.name!r} has invalid regex pattern {self.pattern!r}: {exc}"
                ) from exc
        if self.timeout_seconds < 1:
            raise ValueError(
                f"Check {self.name!r} timeout_seconds must be >= 1, got {self.timeout_seconds}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": self.command,
            "expect": self.expect,
            "pattern": self.pattern,
            "suspected_files": list(self.suspected_files),
            "severity": self.severity,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CheckDefinition":
        raw_files = payload.get("suspected_files", [])
        if not isinstance(raw_files, list):
            raise ValueError(
                "Check definition field 'suspected_files' must be a list of paths"
            )
        return cls(
            name=payload.get("name", ""),
            command=payload.get("command", ""),
            expect=payload.get("expect", "exit_zero"),
            pattern=payload.get("pattern"),
            suspected_files=[str(item) for item in raw_files],
            severity=payload.get("severity", 2),
            timeout_seconds=payload.get("timeout_seconds", 60),
        )


@dataclass(slots=True)
class CheckRunResult:
    check: CheckDefinition
    command_result: CommandResult
    failure: FailureRecord | None


def _shell_command(check: CheckDefinition) -> list[str]:
    return ["sh", "-c", check.command]


def _combine_output(stdout: str, stderr: str) -> str:
    if stdout and stderr and not stdout.endswith("\n"):
        return f"{stdout}\n{stderr}"
    return stdout + stderr


def _truncate_output(value: str) -> str:
    if len(value) <= _OUTPUT_LIMIT:
        return value
    limit = _OUTPUT_LIMIT - len(_TRUNCATION_MARKER)
    return value[:limit] + _TRUNCATION_MARKER


def _build_failure(
    check: CheckDefinition,
    *,
    error_summary: str,
    combined_output: str,
) -> FailureRecord:
    return FailureRecord(
        test_id=check.name,
        error_summary=error_summary,
        raw_excerpt=_truncate_output(combined_output),
        file_path=check.suspected_files[0] if check.suspected_files else None,
        line=None,
    )


def run_check(check: CheckDefinition, repo_root: Path) -> CheckRunResult:
    try:
        result = run_command(
            _shell_command(check),
            cwd=repo_root,
            timeout_seconds=check.timeout_seconds,
            allow_full_env=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        command_result = CommandResult(
            command=check.command,
            returncode=124,
            stdout=stdout,
            stderr=stderr,
        )
        return CheckRunResult(
            check=check,
            command_result=command_result,
            failure=_build_failure(
                check,
                error_summary=f"timeout after {check.timeout_seconds}s",
                combined_output=_combine_output(stdout, stderr),
            ),
        )

    command_result = CommandResult(
        command=check.command,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        duration_seconds=result.duration_seconds,
    )
    combined_output = _combine_output(command_result.stdout, command_result.stderr)

    if check.expect == "exit_zero":
        failure = (
            _build_failure(
                check,
                error_summary=f"exit {command_result.returncode}",
                combined_output=combined_output,
            )
            if command_result.returncode != 0
            else None
        )
        return CheckRunResult(
            check=check,
            command_result=command_result,
            failure=failure,
        )

    assert check.pattern is not None
    matched = re.search(check.pattern, combined_output) is not None
    if check.expect == "matches" and matched:
        return CheckRunResult(
            check=check,
            command_result=command_result,
            failure=_build_failure(
                check,
                error_summary=f"matched /{check.pattern}/",
                combined_output=combined_output,
            ),
        )
    if check.expect == "not_matches" and not matched:
        return CheckRunResult(
            check=check,
            command_result=command_result,
            failure=_build_failure(
                check,
                error_summary=f"missing /{check.pattern}/",
                combined_output=combined_output,
            ),
        )
    return CheckRunResult(check=check, command_result=command_result, failure=None)


def run_checks(checks: list[CheckDefinition], repo_root: Path) -> list[FailureRecord]:
    failures: list[FailureRecord] = []
    for check in checks:
        outcome = run_check(check, repo_root)
        if outcome.failure is not None:
            failures.append(outcome.failure)
    return failures

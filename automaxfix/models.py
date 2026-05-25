from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


def _env_flag(name: str) -> bool | None:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return None
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


@dataclass(slots=True)
class AgentConfig:
    mode: str = "manual_patch_file"
    command: str | None = None
    timeout_seconds: int = 900

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "command": self.command,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "AgentConfig":
        payload = payload or {}
        command = payload.get("command")
        return cls(
            mode=str(payload.get("mode", "manual_patch_file")),
            command=str(command) if command is not None else None,
            timeout_seconds=int(payload.get("timeout_seconds", 900)),
        )


@dataclass(slots=True)
class PatchConfig:
    require_unified_diff: bool = True
    max_patch_attempts: int = 3
    max_files_changed: int = 8
    allow_new_tests: bool = True
    allow_new_source_files: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "require_unified_diff": self.require_unified_diff,
            "max_patch_attempts": self.max_patch_attempts,
            "max_files_changed": self.max_files_changed,
            "allow_new_tests": self.allow_new_tests,
            "allow_new_source_files": self.allow_new_source_files,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "PatchConfig":
        payload = payload or {}
        return cls(
            require_unified_diff=bool(payload.get("require_unified_diff", True)),
            max_patch_attempts=int(payload.get("max_patch_attempts", 3)),
            max_files_changed=int(payload.get("max_files_changed", 8)),
            allow_new_tests=bool(payload.get("allow_new_tests", True)),
            allow_new_source_files=bool(payload.get("allow_new_source_files", False)),
        )


@dataclass(slots=True)
class ApprovalConfig:
    require_human_approval: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"require_human_approval": self.require_human_approval}

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any] | None,
        *,
        default_require_human_approval: bool = True,
    ) -> "ApprovalConfig":
        payload = payload or {}
        return cls(
            require_human_approval=bool(
                payload.get("require_human_approval", default_require_human_approval)
            )
        )


@dataclass(slots=True)
class WatchConfig:
    enabled: bool = True
    default_interval: int = 30
    allowed_runners: list[str] = field(
        default_factory=lambda: ["pytest", "jest", "vitest", "mocha", "go", "cargo"]
    )
    auto_approve_in_watch: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "default_interval": self.default_interval,
            "allowed_runners": list(self.allowed_runners),
            "auto_approve_in_watch": self.auto_approve_in_watch,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "WatchConfig":
        payload = payload or {}
        raw_allowed_runners = payload.get(
            "allowed_runners",
            ["pytest", "jest", "vitest", "mocha", "go", "cargo"],
        )
        if not isinstance(raw_allowed_runners, list):
            raw_allowed_runners = ["pytest", "jest", "vitest", "mocha", "go", "cargo"]
        auto_approve_in_watch = bool(payload.get("auto_approve_in_watch", False))
        env_auto_approve_in_watch = _env_flag("AUTOMAXFIX_WATCH_AUTOAPPROVE")
        if env_auto_approve_in_watch is not None:
            auto_approve_in_watch = env_auto_approve_in_watch
        return cls(
            enabled=bool(payload.get("enabled", True)),
            default_interval=max(1, int(payload.get("default_interval", 30))),
            allowed_runners=list(dict.fromkeys(str(item) for item in raw_allowed_runners)),
            auto_approve_in_watch=auto_approve_in_watch,
        )


@dataclass(slots=True)
class Config:
    repo_path: str = "."
    test_command: str = "pytest -q"
    targeted_test_command: str = "pytest {test_file} -v"
    tickets_dir: str = ".automaxfix/tickets"
    reports_dir: str = ".automaxfix/reports"
    allowed_paths: list[str] = field(default_factory=lambda: ["."])
    blocked_paths: list[str] = field(
        default_factory=lambda: [".git", ".venv", "node_modules", "__pycache__"]
    )
    ci_mode: bool = False
    require_reproduction_test: bool = True
    agent: AgentConfig = field(default_factory=AgentConfig)
    patch: PatchConfig = field(default_factory=PatchConfig)
    approval: ApprovalConfig = field(default_factory=ApprovalConfig)
    watch_mode: WatchConfig = field(default_factory=WatchConfig)

    @property
    def max_files_changed(self) -> int:
        return self.patch.max_files_changed

    @property
    def require_human_approval(self) -> bool:
        return self.approval.require_human_approval

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_path": self.repo_path,
            "test_command": self.test_command,
            "targeted_test_command": self.targeted_test_command,
            "tickets_dir": self.tickets_dir,
            "reports_dir": self.reports_dir,
            "allowed_paths": list(self.allowed_paths),
            "blocked_paths": list(self.blocked_paths),
            "ci_mode": self.ci_mode,
            "require_reproduction_test": self.require_reproduction_test,
            "agent": self.agent.to_dict(),
            "patch": self.patch.to_dict(),
            "approval": self.approval.to_dict(),
            "watch_mode": self.watch_mode.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Config":
        agent_payload = payload.get("agent")
        patch_payload = payload.get("patch")
        approval_payload = payload.get("approval")
        watch_payload = payload.get("watch_mode")
        ci_mode = bool(payload.get("ci_mode", False))
        env_ci_mode = _env_flag("AUTOMAXFIX_CI_MODE")
        if env_ci_mode is not None:
            ci_mode = env_ci_mode
        approval_default = False if ci_mode else True
        return cls(
            repo_path=str(payload.get("repo_path", ".")),
            test_command=str(payload.get("test_command", "pytest -q")),
            targeted_test_command=str(
                payload.get("targeted_test_command", "pytest {test_file} -v")
            ),
            tickets_dir=str(payload.get("tickets_dir", ".automaxfix/tickets")),
            reports_dir=str(payload.get("reports_dir", ".automaxfix/reports")),
            allowed_paths=[str(item) for item in payload.get("allowed_paths", ["."])],
            blocked_paths=[
                str(item)
                for item in payload.get(
                    "blocked_paths", [".git", ".venv", "node_modules", "__pycache__"]
                )
            ],
            ci_mode=ci_mode,
            require_reproduction_test=bool(payload.get("require_reproduction_test", True)),
            agent=AgentConfig.from_dict(agent_payload if isinstance(agent_payload, dict) else None),
            patch=PatchConfig.from_dict(
                patch_payload
                if isinstance(patch_payload, dict)
                else {"max_files_changed": payload.get("max_files_changed", 8)}
            ),
            approval=ApprovalConfig.from_dict(
                approval_payload
                if isinstance(approval_payload, dict)
                else (
                    {"require_human_approval": payload["require_human_approval"]}
                    if "require_human_approval" in payload
                    else None
                ),
                default_require_human_approval=approval_default,
            ),
            watch_mode=WatchConfig.from_dict(watch_payload if isinstance(watch_payload, dict) else None),
        )


class StrategyName(str, Enum):
    MINIMAL = "minimal"
    REFACTOR = "refactor"
    TEST_FIRST = "test_first"
    ROLLBACK = "rollback"


def _strategy_name_from_value(value: Any) -> StrategyName:
    try:
        return StrategyName(str(value))
    except ValueError:
        return StrategyName.MINIMAL


@dataclass(slots=True)
class TicketStrategyAttempt:
    strategy: StrategyName
    reason: str
    agent_used: str
    duration_sec: float
    succeeded: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "reason": self.reason,
            "agent_used": self.agent_used,
            "duration_sec": self.duration_sec,
            "succeeded": self.succeeded,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TicketStrategyAttempt":
        return cls(
            strategy=_strategy_name_from_value(payload.get("strategy", StrategyName.MINIMAL.value)),
            reason=str(payload.get("reason", "")),
            agent_used=str(payload.get("agent_used", "")),
            duration_sec=float(payload.get("duration_sec", 0.0)),
            succeeded=bool(payload.get("succeeded", False)),
        )


@dataclass(slots=True)
class TicketStrategyMemo:
    attempts: list[TicketStrategyAttempt] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"attempts": [attempt.to_dict() for attempt in self.attempts]}

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "TicketStrategyMemo":
        payload = payload or {}
        raw_attempts = payload.get("attempts", [])
        return cls(
            attempts=[
                TicketStrategyAttempt.from_dict(item)
                for item in raw_attempts
                if isinstance(item, dict)
            ]
        )

    def exhausted_strategies(self) -> set[StrategyName]:
        return {attempt.strategy for attempt in self.attempts if not attempt.succeeded}

    def last_attempt(self) -> TicketStrategyAttempt | None:
        if not self.attempts:
            return None
        return self.attempts[-1]


@dataclass(slots=True)
class Ticket:
    id: str
    created_at: str
    source: str
    title: str
    bug_report: str
    github_actions_run_url: str | None = None
    severity: int = 1
    status: str = "new"
    suspected_files: list[str] = field(default_factory=list)
    reproduction_test: str | None = None
    patch_summary: str | None = None
    tests_run: list[str] = field(default_factory=list)
    result: str | None = None
    strategy_memo: TicketStrategyMemo = field(default_factory=TicketStrategyMemo)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "source": self.source,
            "title": self.title,
            "bug_report": self.bug_report,
            "github_actions_run_url": self.github_actions_run_url,
            "severity": self.severity,
            "status": self.status,
            "suspected_files": list(self.suspected_files),
            "reproduction_test": self.reproduction_test,
            "patch_summary": self.patch_summary,
            "tests_run": list(self.tests_run),
            "result": self.result,
            "strategy_memo": self.strategy_memo.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Ticket":
        return cls(
            id=str(payload["id"]),
            created_at=str(payload["created_at"]),
            source=str(payload["source"]),
            title=str(payload["title"]),
            bug_report=str(payload["bug_report"]),
            github_actions_run_url=(
                str(payload["github_actions_run_url"])
                if payload.get("github_actions_run_url") is not None
                else None
            ),
            severity=int(payload.get("severity", 1)),
            status=str(payload.get("status", "new")),
            suspected_files=[str(item) for item in payload.get("suspected_files", [])],
            reproduction_test=(
                str(payload["reproduction_test"])
                if payload.get("reproduction_test") is not None
                else None
            ),
            patch_summary=(
                str(payload["patch_summary"])
                if payload.get("patch_summary") is not None
                else None
            ),
            tests_run=[str(item) for item in payload.get("tests_run", [])],
            result=str(payload["result"]) if payload.get("result") is not None else None,
            strategy_memo=TicketStrategyMemo.from_dict(
                payload["strategy_memo"]
                if isinstance(payload.get("strategy_memo"), dict)
                else None
            ),
        )


@dataclass(slots=True)
class ParsedFailure:
    node_id: str
    message: str
    suspected_file: str


@dataclass(slots=True)
class FailureRecord:
    test_id: str
    error_summary: str
    raw_excerpt: str
    file_path: str | None = None
    line: int | None = None


@dataclass(slots=True)
class PatchFileChange:
    path: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "content": self.content}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PatchFileChange":
        return cls(path=str(payload["path"]), content=str(payload["content"]))


@dataclass(slots=True)
class PatchProposal:
    summary: str
    files: list[PatchFileChange] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"summary": self.summary, "files": [item.to_dict() for item in self.files]}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PatchProposal":
        return cls(
            summary=str(payload.get("summary", "")),
            files=[PatchFileChange.from_dict(item) for item in payload.get("files", [])],
        )


@dataclass(slots=True)
class RepoContext:
    repo_root: Path
    top_level_entries: list[str]
    suspected_files: list[dict[str, str]]


@dataclass(slots=True)
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float = 0.0

    @property
    def passed(self) -> bool:
        return self.returncode == 0


@dataclass(slots=True)
class PatchChange:
    path: str
    old_path: str | None
    new_path: str | None
    is_new: bool = False
    is_deleted: bool = False
    added_lines: list[str] = field(default_factory=list)
    removed_lines: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PatchValidationResult:
    valid: bool
    retryable_invalid_diff: bool = False
    errors: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    new_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    patch_changes: list[PatchChange] = field(default_factory=list)


@dataclass(slots=True)
class AgentRunResult:
    mode: str
    patch_text: str
    agent_used: str | None = None
    prompt_file: Path | None = None
    patch_file: Path | None = None
    command: str | None = None
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    duration_seconds: float = 0.0
    attempt_count: int = 1
    invalid_diff_retries: int = 0
    validation_errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AgentAttempt:
    attempt_number: int
    mode: str
    agent_used: str
    strategy: StrategyName | None = None
    prompt_file: Path | None = None
    output_file: Path | None = None
    command: str | None = None
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    duration_seconds: float = 0.0
    is_valid_diff: bool = False
    validation_errors: list[str] = field(default_factory=list)
    retryable_invalid_diff: bool = False


@dataclass(slots=True)
class WorkspaceStatus:
    repo_root: Path
    is_git_repo: bool
    is_dirty: bool
    git_root: Path | None = None
    status_lines: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ApprovalDecision:
    approved: bool
    requires_confirmation: bool
    reason: str

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import CommandResult


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_directory(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def slugify(value: str, *, max_length: int = 40) -> str:
    lowered = value.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    if not normalized:
        normalized = "ticket"
    return normalized[:max_length].rstrip("_") or "ticket"


def resolve_path(base_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_dir / candidate).resolve()


def truncate(value: str, *, limit: int = 500) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def tail_text(value: str, *, lines: int = 20, max_chars: int = 1200) -> str:
    if not value:
        return ""
    clipped_lines = value.splitlines()[-lines:]
    clipped = "\n".join(clipped_lines)
    return truncate(clipped, limit=max_chars)


def env_flag(name: str) -> bool | None:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return None
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def github_actions_run_url() -> str | None:
    server_url = os.environ.get("GITHUB_SERVER_URL", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    if not server_url or not repository or not run_id:
        return None
    return f"{server_url}/{repository}/actions/runs/{run_id}"


def clear_python_caches(repo_root: Path) -> None:
    # Avoid stale timestamp-based .pyc reuse after a rapid patch apply.
    for cache_dir in repo_root.rglob("__pycache__"):
        if not cache_dir.is_dir():
            continue
        for child in cache_dir.iterdir():
            if child.is_file():
                child.unlink(missing_ok=True)
        cache_dir.rmdir()


def run_command(
    argv: list[str],
    *,
    cwd: Path,
    timeout_seconds: int | None = None,
    env: dict[str, str] | None = None,
    pythonpath_root: Path | None = None,
) -> CommandResult:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    if pythonpath_root is not None:
        existing_pythonpath = merged_env.get("PYTHONPATH", "")
        root = str(pythonpath_root)
        merged_env["PYTHONPATH"] = (
            root if not existing_pythonpath else root + os.pathsep + existing_pythonpath
        )
    start = time.monotonic()
    completed = subprocess.run(
        argv,
        cwd=str(cwd),
        env=merged_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    duration_seconds = time.monotonic() - start
    return CommandResult(
        command=" ".join(argv),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_seconds=duration_seconds,
    )

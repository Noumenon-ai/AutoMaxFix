from __future__ import annotations

import re
from pathlib import Path

from ..models import FailureRecord

_FAILED_PATTERN = re.compile(r"^FAILED\s+([^\s]+)\s+-\s+(.+)$", re.MULTILINE)
_ERROR_PATTERN = re.compile(r"^ERROR\s+([^\s]+)\s+-\s+(.+)$", re.MULTILINE)


def _build_records(matches: list[tuple[str, str]]) -> list[FailureRecord]:
    return [
        FailureRecord(
            test_id=node_id.strip(),
            file_path=node_id.split("::", 1)[0].strip(),
            line=None,
            error_summary=message.strip(),
            raw_excerpt=f"{node_id.strip()} - {message.strip()}",
        )
        for node_id, message in matches
    ]


def scan(text: str, repo_root: Path) -> list[FailureRecord]:
    del repo_root
    failed = _build_records(_FAILED_PATTERN.findall(text))
    if failed:
        return failed
    return _build_records(_ERROR_PATTERN.findall(text))

from __future__ import annotations

import re
from pathlib import Path

from ..models import FailureRecord
from ._common import normalize_file_path


_GENERIC_PATTERN = re.compile(
    r"(?P<path>(?:[A-Za-z]:)?(?:[^\s:()]+[/\\])*[^\s:()]+\.[A-Za-z0-9_]+)"
    r":(?P<line>\d+)(?::(?P<column>\d+))?:\s*(?P<message>.+)"
)


def scan(text: str, repo_root: Path) -> list[FailureRecord]:
    records: list[FailureRecord] = []
    for line in text.splitlines():
        match = _GENERIC_PATTERN.search(line)
        if match is None:
            continue
        file_path = normalize_file_path(match.group("path"), repo_root)
        line_number = int(match.group("line"))
        message = match.group("message").strip()
        if not message:
            continue
        records.append(
            FailureRecord(
                test_id=f"{file_path}:{line_number}",
                file_path=file_path,
                line=line_number,
                error_summary=message,
                raw_excerpt=line.strip(),
            )
        )
    return records

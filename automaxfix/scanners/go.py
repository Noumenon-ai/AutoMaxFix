from __future__ import annotations

import re
from pathlib import Path

from ..models import FailureRecord
from ._common import extract_location, first_summary_line, normalize_file_path

_FAIL_PATTERN = re.compile(r"^--- FAIL: (\S+)(?: \([^)]+\))?$", re.MULTILINE)
_DETAIL_PATTERN = re.compile(
    r"^\s+(?P<path>[^\s:][^:]*\.[A-Za-z0-9_]+):(?P<line>\d+):\s*(?P<message>.+)$",
    re.MULTILINE,
)


def scan(text: str, repo_root: Path) -> list[FailureRecord]:
    records: list[FailureRecord] = []
    matches = list(_FAIL_PATTERN.finditer(text))
    for index, match in enumerate(matches):
        block_end = (
            matches[index + 1].start() if index + 1 < len(matches) else len(text)
        )
        block = text[match.start() : block_end].strip()
        detail_match = _DETAIL_PATTERN.search(block)
        if detail_match is not None:
            file_path = normalize_file_path(detail_match.group("path"), repo_root)
            line = int(detail_match.group("line"))
            summary = detail_match.group("message").strip()
        else:
            file_path, line = extract_location(block, repo_root)
            summary = first_summary_line(block.splitlines()[1:]) or "Test failed."
        records.append(
            FailureRecord(
                test_id=match.group(1).strip(),
                file_path=file_path,
                line=line,
                error_summary=summary,
                raw_excerpt=block,
            )
        )
    return records

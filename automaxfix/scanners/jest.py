from __future__ import annotations

import re
from pathlib import Path

from ..models import FailureRecord
from ._common import LOCATION_PATTERN, first_summary_line, normalize_file_path


_FAIL_PATTERN = re.compile(r"^FAIL\s+(.+)$", re.MULTILINE)
_TEST_PATTERN = re.compile(r"^\s*●\s+(.+)$", re.MULTILINE)
_SKIP_PATTERN = re.compile(r"^[>\|\^+\-\d\s]+$")


def _fail_file_path(header: str, repo_root: Path) -> str:
    candidate = header.strip()
    if " (" in candidate:
        candidate = candidate.split(" (", 1)[0].rstrip()
    return normalize_file_path(candidate, repo_root)


def _summary_from_block(block: str) -> str:
    lines = block.splitlines()
    summary = first_summary_line(
        lines[1:],
        skip_prefixes=("●", "at ", "FAIL", "Expected:", "Received:", "Snapshot:"),
        skip_pattern=_SKIP_PATTERN,
    )
    return summary or "Test failed."


def _preferred_location(block: str, file_path: str, repo_root: Path) -> tuple[str | None, int | None]:
    candidates = [
        (normalize_file_path(match.group("path"), repo_root), int(match.group("line")))
        for match in LOCATION_PATTERN.finditer(block)
    ]
    for candidate_path, candidate_line in candidates:
        if candidate_path == file_path:
            return candidate_path, candidate_line
    for candidate_path, candidate_line in candidates:
        if "node_modules/" not in candidate_path:
            return candidate_path, candidate_line
    if candidates:
        return candidates[0]
    return None, None


def scan(text: str, repo_root: Path) -> list[FailureRecord]:
    records: list[FailureRecord] = []
    matches = list(_FAIL_PATTERN.finditer(text))
    for index, match in enumerate(matches):
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start() : block_end].strip()
        file_path = _fail_file_path(match.group(1), repo_root)
        test_matches = list(_TEST_PATTERN.finditer(block))
        if not test_matches:
            location_file, line = _preferred_location(block, file_path, repo_root)
            records.append(
                FailureRecord(
                    test_id=file_path,
                    file_path=location_file or file_path,
                    line=line,
                    error_summary=_summary_from_block(block),
                    raw_excerpt=block,
                )
            )
            continue

        for test_index, test_match in enumerate(test_matches):
            section_end = (
                test_matches[test_index + 1].start()
                if test_index + 1 < len(test_matches)
                else len(block)
            )
            section = block[test_match.start() : section_end].strip()
            location_file, line = _preferred_location(section, file_path, repo_root)
            records.append(
                FailureRecord(
                    test_id=test_match.group(1).strip(),
                    file_path=location_file or file_path,
                    line=line,
                    error_summary=_summary_from_block(section),
                    raw_excerpt=section,
                )
            )
    return records

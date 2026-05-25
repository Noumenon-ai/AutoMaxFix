from __future__ import annotations

import re
from pathlib import Path

from ..models import FailureRecord
from ._common import extract_location, first_summary_line


_SPEC_PATTERN = re.compile(r"^\s*\d+\)\s+(.+)$", re.MULTILINE)
_TAP_PATTERN = re.compile(r"^not ok\s+\d+\s+(.+)$", re.MULTILINE)
_MESSAGE_PATTERN = re.compile(r"^\s*message:\s*(.+)$", re.MULTILINE)
_AT_PATTERN = re.compile(r"^\s*at:\s*(.+)$", re.MULTILINE)
_FAILING_SUMMARY_PATTERN = re.compile(r"^\s*\d+\s+failing\b.*$", re.MULTILINE)


def _scan_spec(text: str, repo_root: Path) -> list[FailureRecord]:
    records: list[FailureRecord] = []
    summary_match = _FAILING_SUMMARY_PATTERN.search(text)
    detail_text = text[summary_match.end() :] if summary_match else text
    matches = list(_SPEC_PATTERN.finditer(detail_text))
    for index, match in enumerate(matches):
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(detail_text)
        block = detail_text[match.start() : block_end].strip()
        lines = block.splitlines()
        test_parts = [re.sub(r"^\s*\d+\)\s+", "", lines[0]).strip().rstrip(":")]
        cursor = 1
        while cursor < len(lines):
            stripped = lines[cursor].strip()
            if not stripped:
                cursor += 1
                continue
            if stripped.startswith(("at ", "Assertion", "Error", "TypeError", "ReferenceError")):
                break
            if stripped.endswith(":"):
                test_parts.append(stripped[:-1].strip())
                cursor += 1
                continue
            break

        location_file, line = extract_location(block, repo_root)
        if location_file is None or line is None:
            continue
        summary = first_summary_line(lines[cursor:], skip_prefixes=("at ",)) or "Test failed."
        records.append(
            FailureRecord(
                test_id=" ".join(part for part in test_parts if part),
                file_path=location_file,
                line=line,
                error_summary=summary,
                raw_excerpt=block,
            )
        )
    return records


def _scan_tap(text: str, repo_root: Path) -> list[FailureRecord]:
    records: list[FailureRecord] = []
    matches = list(_TAP_PATTERN.finditer(text))
    for index, match in enumerate(matches):
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start() : block_end].strip()
        at_match = _AT_PATTERN.search(block)
        location_file, line = extract_location(at_match.group(1), repo_root) if at_match else (None, None)
        summary_match = _MESSAGE_PATTERN.search(block)
        summary = summary_match.group(1).strip() if summary_match else "Test failed."
        records.append(
            FailureRecord(
                test_id=match.group(1).strip(),
                file_path=location_file,
                line=line,
                error_summary=summary,
                raw_excerpt=block,
            )
        )
    return records


def scan(text: str, repo_root: Path) -> list[FailureRecord]:
    records = _scan_tap(text, repo_root)
    if records:
        return records
    return _scan_spec(text, repo_root)

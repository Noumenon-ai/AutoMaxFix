from __future__ import annotations

import re
from pathlib import Path

from ..models import FailureRecord
from ._common import extract_location, first_summary_line, normalize_file_path


_FAILED_TEST_PATTERN = re.compile(r"^test\s+(.+?)\s+\.\.\.\s+FAILED$", re.MULTILINE)
_SECTION_PATTERN = re.compile(r"^----\s+(.+?)\s+(stdout|stderr)\s+----$", re.MULTILINE)
_PANIC_PATTERN = re.compile(
    r"panicked at (?P<path>(?:[A-Za-z]:)?(?:[^\s:()]+[/\\])*[^\s:()]+\.[A-Za-z0-9_]+)"
    r":(?P<line>\d+)(?::\d+)?:"
)


def _section_blocks(text: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    matches = list(_SECTION_PATTERN.finditer(text))
    for index, match in enumerate(matches):
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks[match.group(1).strip()] = text[match.start() : block_end].strip()
    return blocks


def _summary_from_block(block: str) -> str:
    lines = block.splitlines()
    for index, line in enumerate(lines):
        if "panicked at " not in line:
            continue
        summary = first_summary_line(lines[index + 1 :], skip_prefixes=("note:",))
        if summary is not None:
            return summary
        return line.strip()
    summary = first_summary_line(lines[1:], skip_prefixes=("note:",))
    return summary or "Test failed."


def scan(text: str, repo_root: Path) -> list[FailureRecord]:
    records: list[FailureRecord] = []
    failed_tests = [match.group(1).strip() for match in _FAILED_TEST_PATTERN.finditer(text)]
    section_blocks = _section_blocks(text)

    for test_id in failed_tests:
        block = section_blocks.get(test_id, f"test {test_id} ... FAILED")
        panic_match = _PANIC_PATTERN.search(block)
        if panic_match is not None:
            file_path = normalize_file_path(panic_match.group("path"), repo_root)
            line = int(panic_match.group("line"))
        else:
            file_path, line = extract_location(block, repo_root)
        records.append(
            FailureRecord(
                test_id=test_id,
                file_path=file_path,
                line=line,
                error_summary=_summary_from_block(block),
                raw_excerpt=block,
            )
        )
    return records

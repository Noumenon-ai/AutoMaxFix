from __future__ import annotations

import re
from pathlib import Path

from ..models import FailureRecord
from ._common import extract_location, first_summary_line, normalize_file_path


_FAIL_PATTERN = re.compile(r"^\s*FAIL\s+(.+)$", re.MULTILINE)
_SKIP_PATTERN = re.compile(r"^[>\|\^+\-\d\s]+$")


def _split_descriptor(descriptor: str, repo_root: Path) -> tuple[str, str]:
    parts = [part.strip() for part in descriptor.split(" > ") if part.strip()]
    file_path = normalize_file_path(parts[0], repo_root)
    test_id = " > ".join(parts[1:]) or file_path
    return file_path, test_id


def _summary_from_block(block: str) -> str:
    lines = block.splitlines()
    summary = first_summary_line(
        lines[1:],
        skip_prefixes=("❯", "at ", "FAIL", "Serialized Error:", "Caused by:"),
        skip_pattern=_SKIP_PATTERN,
    )
    return summary or "Test failed."


def scan(text: str, repo_root: Path) -> list[FailureRecord]:
    records: list[FailureRecord] = []
    matches = list(_FAIL_PATTERN.finditer(text))
    for index, match in enumerate(matches):
        descriptor = match.group(1).strip()
        if "." not in Path(descriptor.split(" > ", 1)[0]).name:
            continue
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start() : block_end].strip()
        file_path, test_id = _split_descriptor(descriptor, repo_root)
        location_file, line = extract_location(block, repo_root)
        records.append(
            FailureRecord(
                test_id=test_id,
                file_path=location_file or file_path,
                line=line,
                error_summary=_summary_from_block(block),
                raw_excerpt=block,
            )
        )
    return records

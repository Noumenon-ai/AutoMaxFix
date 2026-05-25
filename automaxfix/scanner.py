from __future__ import annotations

from pathlib import Path

from .models import ParsedFailure
from .scanners.pytest import scan as scan_pytest


def parse_pytest_output(text: str) -> list[ParsedFailure]:
    return [
        ParsedFailure(
            node_id=record.test_id,
            message=record.error_summary,
            suspected_file=record.file_path or record.test_id.split("::", 1)[0].strip(),
        )
        for record in scan_pytest(text, Path("."))
    ]


def scan_pytest_output_file(path: Path) -> list[ParsedFailure]:
    return parse_pytest_output(path.read_text(encoding="utf-8"))

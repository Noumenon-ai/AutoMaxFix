from __future__ import annotations

import re
from pathlib import Path


LOCATION_PATTERN = re.compile(
    r"(?P<path>(?:[A-Za-z]:)?(?:[^\s:()]+[/\\])*[^\s:()]+\.[A-Za-z0-9_]+)"
    r":(?P<line>\d+)(?::(?P<column>\d+))?"
)


def normalize_file_path(path_text: str, repo_root: Path) -> str:
    cleaned = path_text.strip().strip("\"'`()[]")
    cleaned = cleaned.removeprefix("file://").replace("\\", "/")
    if cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if not cleaned:
        return cleaned

    path = Path(cleaned)
    if path.is_absolute():
        try:
            return str(path.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            try:
                return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
            except (OSError, RuntimeError, ValueError):
                return str(path).replace("\\", "/")
    return cleaned


def extract_location(text: str, repo_root: Path) -> tuple[str | None, int | None]:
    match = LOCATION_PATTERN.search(text)
    if match is None:
        return None, None
    return normalize_file_path(match.group("path"), repo_root), int(match.group("line"))


def first_summary_line(
    lines: list[str],
    *,
    skip_prefixes: tuple[str, ...] = (),
    skip_pattern: re.Pattern[str] | None = None,
) -> str | None:
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if skip_prefixes and stripped.startswith(skip_prefixes):
            continue
        if skip_pattern is not None and skip_pattern.search(stripped):
            continue
        return stripped
    return None

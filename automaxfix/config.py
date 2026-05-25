from __future__ import annotations

import ast
from pathlib import Path

from .models import Config
from .utils import ensure_directory


class ConfigError(RuntimeError):
    """Raised when config parsing fails."""


DEFAULT_CONFIG = Config()


def render_default_config() -> str:
    return """repo_path: "."
test_command: "pytest -q"
targeted_test_command: "pytest {test_file} -v"
tickets_dir: ".automaxfix/tickets"
reports_dir: ".automaxfix/reports"
allowed_paths:
  - "."
blocked_paths:
  - ".git"
  - ".venv"
  - "node_modules"
  - "__pycache__"
ci_mode: false
require_reproduction_test: true
agent:
  mode: "manual_patch_file"
  command: null
  timeout_seconds: 900
patch:
  require_unified_diff: true
  max_patch_attempts: 3
  max_files_changed: 8
  allow_new_tests: true
  allow_new_source_files: false
approval:
  require_human_approval: true
watch_mode:
  enabled: true
  default_interval: 30
  allowed_runners:
    - "pytest"
    - "jest"
    - "vitest"
    - "mocha"
    - "go"
    - "cargo"
  auto_approve_in_watch: false
"""


def _parse_scalar(raw: str):
    value = raw.strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    if value.startswith(('"', "'")) and value.endswith(('"', "'")):
        return ast.literal_eval(value)
    if value.lstrip("-").isdigit():
        return int(value)
    return value


def _tokenize(text: str) -> list[tuple[int, int, str]]:
    tokens: list[tuple[int, int, str]] = []
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "\t" in raw_line[: len(raw_line) - len(raw_line.lstrip())]:
            raise ConfigError(f"Line {lineno}: tabs are not supported")
        indent = len(line) - len(line.lstrip(" "))
        tokens.append((lineno, indent, stripped))
    return tokens


def _parse_list(tokens: list[tuple[int, int, str]], index: int, indent: int) -> tuple[list[object], int]:
    items: list[object] = []
    while index < len(tokens):
        lineno, line_indent, content = tokens[index]
        if line_indent < indent:
            break
        if line_indent != indent or not content.startswith("- "):
            break
        raw_value = content[2:].strip()
        if not raw_value:
            raise ConfigError(f"Line {lineno}: nested list items are not supported")
        items.append(_parse_scalar(raw_value))
        index += 1
    return items, index


def _parse_mapping(
    tokens: list[tuple[int, int, str]], index: int, indent: int
) -> tuple[dict[str, object], int]:
    payload: dict[str, object] = {}
    while index < len(tokens):
        lineno, line_indent, content = tokens[index]
        if line_indent < indent:
            break
        if line_indent != indent:
            raise ConfigError(f"Line {lineno}: unexpected indentation")
        if content.startswith("- "):
            raise ConfigError(f"Line {lineno}: list item without a parent key")
        if ":" not in content:
            raise ConfigError(f"Line {lineno}: expected key: value")

        key, raw_value = content.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        index += 1

        if value:
            payload[key] = _parse_scalar(value)
            continue

        if index >= len(tokens):
            payload[key] = {}
            continue

        _, next_indent, next_content = tokens[index]
        if next_indent <= line_indent:
            payload[key] = {}
            continue
        if next_content.startswith("- "):
            parsed_list, index = _parse_list(tokens, index, next_indent)
            payload[key] = parsed_list
            continue
        parsed_mapping, index = _parse_mapping(tokens, index, next_indent)
        payload[key] = parsed_mapping
    return payload, index


def parse_config_text(text: str) -> Config:
    tokens = _tokenize(text)
    if not tokens:
        return Config.from_dict({})
    payload, index = _parse_mapping(tokens, 0, tokens[0][1])
    if index != len(tokens):
        lineno = tokens[index][0]
        raise ConfigError(f"Line {lineno}: could not parse config")
    return Config.from_dict(payload)


def load_config(base_dir: Path, config_path: str | None = None) -> Config:
    path = resolve_config_path(base_dir, config_path=config_path)
    if path is None:
        return Config.from_dict({})
    return parse_config_text(path.read_text(encoding="utf-8"))


def resolve_config_path(base_dir: Path, config_path: str | None = None) -> Path | None:
    if config_path:
        path = Path(config_path)
        if not path.is_absolute():
            path = (base_dir / path).resolve()
        return path
    candidates = [
        (base_dir / ".automaxfix" / "config.yml").resolve(),
        (base_dir / "automaxfix.yml").resolve(),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def write_default_config(destination: Path) -> Path:
    ensure_directory(destination.parent)
    destination.write_text(render_default_config(), encoding="utf-8")
    return destination

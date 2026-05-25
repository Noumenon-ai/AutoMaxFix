from __future__ import annotations

from pathlib import Path

from automaxfix.config import load_config, parse_config_text, render_default_config, write_default_config


def test_parse_default_config_text() -> None:
    config = parse_config_text(render_default_config())
    assert config.repo_path == "."
    assert config.test_command == "pytest -q"
    assert config.allowed_paths == ["."]
    assert config.blocked_paths == [".git", ".venv", "node_modules", "__pycache__"]
    assert config.ci_mode is False
    assert config.agent.mode == "manual_patch_file"
    assert config.patch.max_patch_attempts == 3
    assert config.patch.max_files_changed == 8
    assert config.approval.require_human_approval is True
    assert config.watch_mode.enabled is True
    assert config.watch_mode.default_interval == 30
    assert config.watch_mode.allowed_runners == ["pytest", "jest", "vitest", "mocha", "go", "cargo"]
    assert config.watch_mode.auto_approve_in_watch is False


def test_load_config_from_dot_automaxfix(tmp_path: Path) -> None:
    config_path = tmp_path / ".automaxfix" / "config.yml"
    write_default_config(config_path)
    config = load_config(tmp_path)
    assert config.tickets_dir == ".automaxfix/tickets"
    assert config.reports_dir == ".automaxfix/reports"
    assert config.agent.timeout_seconds == 900


def test_parse_config_supports_explicit_ci_mode() -> None:
    config = parse_config_text(
        """
repo_path: "."
ci_mode: true
"""
    )
    assert config.ci_mode is True
    assert config.approval.require_human_approval is False


def test_load_config_allows_ci_mode_env_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOMAXFIX_CI_MODE", "1")
    config = load_config(tmp_path)
    assert config.ci_mode is True
    assert config.approval.require_human_approval is False


def test_parse_config_supports_watch_mode_block() -> None:
    config = parse_config_text(
        """
repo_path: "."
watch_mode:
  enabled: true
  default_interval: 12
  allowed_runners:
    - "pytest"
    - "generic"
  auto_approve_in_watch: true
"""
    )
    assert config.watch_mode.enabled is True
    assert config.watch_mode.default_interval == 12
    assert config.watch_mode.allowed_runners == ["pytest", "generic"]
    assert config.watch_mode.auto_approve_in_watch is True


def test_load_config_allows_watch_autoapprove_env_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOMAXFIX_WATCH_AUTOAPPROVE", "1")
    config = load_config(tmp_path)
    assert config.watch_mode.auto_approve_in_watch is True

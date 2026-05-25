from __future__ import annotations

from pathlib import Path

from .models import CommandResult, Config
from .safety import validate_command
from .utils import clear_python_caches, run_command


def run_targeted_test(config: Config, repo_root: Path, test_file: str) -> CommandResult:
    command = config.targeted_test_command.format(test_file=test_file)
    argv = validate_command(command=command, config=config, kind="targeted", test_file=test_file)
    clear_python_caches(repo_root)
    return run_command(argv, cwd=repo_root, pythonpath_root=repo_root)


def run_regression_suite(config: Config, repo_root: Path) -> CommandResult:
    command = config.test_command
    argv = validate_command(command=command, config=config, kind="regression")
    clear_python_caches(repo_root)
    return run_command(argv, cwd=repo_root, pythonpath_root=repo_root)

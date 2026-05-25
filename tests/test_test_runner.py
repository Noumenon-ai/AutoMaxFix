from __future__ import annotations

from pathlib import Path

from automaxfix.models import Config
from automaxfix.test_runner import run_regression_suite, run_targeted_test


def test_test_runner_executes_targeted_and_regression(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text(
        "def test_truth():\n    assert 2 + 2 == 4\n",
        encoding="utf-8",
    )
    config = Config()
    targeted = run_targeted_test(config, tmp_path, "tests/test_sample.py")
    regression = run_regression_suite(config, tmp_path)
    assert targeted.passed is True
    assert regression.passed is True

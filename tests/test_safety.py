from __future__ import annotations

from pathlib import Path

import pytest

from automaxfix.models import Config, PatchConfig, PatchFileChange, PatchProposal
from automaxfix.safety import SafetyError, split_safe_command, validate_command, validate_edit_path, validate_patch_proposal


def test_validate_edit_path_blocks_sensitive_targets(tmp_path: Path) -> None:
    config = Config()
    with pytest.raises(SafetyError):
        validate_edit_path(tmp_path, config, ".env")
    with pytest.raises(SafetyError):
        validate_edit_path(tmp_path, config, ".git/config")


def test_validate_command_rejects_package_installs() -> None:
    config = Config()
    with pytest.raises(SafetyError):
        validate_command(command="pip install requests", config=config, kind="regression")


def test_validate_patch_proposal_blocks_too_many_files(tmp_path: Path) -> None:
    config = Config(patch=PatchConfig(max_files_changed=1))
    proposal = PatchProposal(
        summary="Too large",
        files=[
            PatchFileChange(path="a.py", content="print('a')\n"),
            PatchFileChange(path="b.py", content="print('b')\n"),
        ],
    )
    with pytest.raises(SafetyError):
        validate_patch_proposal(tmp_path, config, proposal)


def test_split_safe_command_blocks_shell_redirects() -> None:
    with pytest.raises(SafetyError):
        split_safe_command("python3 agent.py > output.diff")

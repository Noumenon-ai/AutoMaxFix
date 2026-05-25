from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_ci_workflow_and_action_yaml_are_valid() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "automaxfix-on-fail.yml").read_text())
    action = yaml.safe_load((ROOT / ".github" / "actions" / "automaxfix-action" / "action.yml").read_text())

    assert workflow["name"] == "AutoMaxFix On Fail"
    assert action["runs"]["using"] == "composite"

    action_inputs = action["inputs"]
    for key in ["test-runner", "test-output-path", "agent", "require-approval", "open-pr"]:
        assert key in action_inputs
    assert action_inputs["agent"]["default"] == "codex_cli"
    assert action_inputs["require-approval"]["default"] == "true"
    assert action_inputs["open-pr"]["default"] == "true"

    workflow_inputs = workflow["on"]["workflow_call"]["inputs"]
    for key in ["test-runner", "test-output-path", "agent", "require-approval", "open-pr"]:
        assert key in workflow_inputs
    assert workflow_inputs["agent"]["default"] == "codex_cli"
    assert workflow_inputs["require-approval"]["default"] is True
    assert workflow_inputs["open-pr"]["default"] is True

    workflow_steps = workflow["jobs"]["automaxfix"]["steps"]
    assert any(step.get("uses") == "./.github/actions/automaxfix-action" for step in workflow_steps)

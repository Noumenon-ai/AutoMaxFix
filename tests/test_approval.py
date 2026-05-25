from __future__ import annotations

from automaxfix.approval import evaluate_approval
from automaxfix.models import ApprovalConfig, Config


def test_approval_requires_confirmation_for_dirty_workspace() -> None:
    config = Config()
    decision = evaluate_approval(config, approved=False, workspace_dirty=True)
    assert decision.approved is False
    assert decision.requires_confirmation is True
    assert "Workspace is dirty" in decision.reason


def test_approval_allows_non_interactive_run_when_disabled() -> None:
    config = Config(approval=ApprovalConfig(require_human_approval=False))
    decision = evaluate_approval(config, approved=False, workspace_dirty=False)
    assert decision.approved is True
    assert decision.requires_confirmation is False

from __future__ import annotations

from .models import ApprovalDecision, Config


def evaluate_approval(
    config: Config,
    *,
    approved: bool,
    workspace_dirty: bool,
) -> ApprovalDecision:
    if approved:
        return ApprovalDecision(
            approved=True,
            requires_confirmation=False,
            reason="Approved by operator.",
        )
    if workspace_dirty:
        return ApprovalDecision(
            approved=False,
            requires_confirmation=True,
            reason="Workspace is dirty. Re-run with --yes after review.",
        )
    if config.approval.require_human_approval:
        return ApprovalDecision(
            approved=False,
            requires_confirmation=True,
            reason="Human approval required. Re-run with --yes.",
        )
    return ApprovalDecision(
        approved=True,
        requires_confirmation=False,
        reason="Human approval not required by config.",
    )

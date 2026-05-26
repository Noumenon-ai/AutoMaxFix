from __future__ import annotations

from pathlib import Path

from .models import Config, PatchFileChange, PatchProposal, RepoContext, Ticket
from .safety import validate_edit_path, validate_patch_proposal
from .utils import ensure_directory, truncate


def inspect_repo(
    ticket: Ticket, repo_root: Path, *, preview_chars: int = 600
) -> RepoContext:
    top_level_entries = sorted(
        item.name
        for item in repo_root.iterdir()
        if item.name not in {".automaxfix", ".git"}
    )
    suspected_files: list[dict[str, str]] = []
    for raw_path in ticket.suspected_files[:6]:
        path = repo_root / raw_path
        if not path.exists() or not path.is_file():
            continue
        suspected_files.append(
            {
                "path": raw_path,
                "excerpt": truncate(
                    path.read_text(encoding="utf-8", errors="replace"),
                    limit=preview_chars,
                ),
            }
        )
    return RepoContext(
        repo_root=repo_root,
        top_level_entries=top_level_entries[:30],
        suspected_files=suspected_files,
    )


def build_patch_plan(ticket: Ticket, repo_context: RepoContext) -> list[str]:
    plan = [f"Investigate ticket {ticket.id}: {ticket.title}."]
    if ticket.suspected_files:
        plan.append(
            "Inspect suspected files: " + ", ".join(ticket.suspected_files) + "."
        )
    else:
        plan.append("Inspect failing tests and likely touched modules to narrow scope.")
    if ticket.reproduction_test:
        plan.append(
            f"Create or confirm reproduction test at {ticket.reproduction_test}."
        )
    plan.append("Generate a minimal patch that changes one bug at a time.")
    plan.append("Run targeted tests first, then regression.")
    if not repo_context.suspected_files:
        plan.append("Repo context is shallow, so keep the first patch conservative.")
    return plan


def merge_reproduction_into_patch(
    proposal: PatchProposal,
    *,
    reproduction_path: str | None,
    reproduction_content: str | None,
) -> PatchProposal:
    if not reproduction_path or not reproduction_content:
        return proposal
    existing_paths = {item.path for item in proposal.files}
    files = list(proposal.files)
    if reproduction_path not in existing_paths:
        files.insert(
            0, PatchFileChange(path=reproduction_path, content=reproduction_content)
        )
    return PatchProposal(summary=proposal.summary, files=files)


def apply_patch_proposal(
    proposal: PatchProposal,
    *,
    repo_root: Path,
    config: Config,
) -> list[Path]:
    validate_patch_proposal(repo_root, config, proposal)
    changed_paths: list[Path] = []
    for change in proposal.files:
        path = validate_edit_path(repo_root, config, change.path)
        ensure_directory(path.parent)
        path.write_text(change.content, encoding="utf-8")
        changed_paths.append(path)
    return changed_paths

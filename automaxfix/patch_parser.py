from __future__ import annotations

import re
from pathlib import Path

from .models import Config, PatchChange, PatchValidationResult
from .safety import SafetyError, contains_dangerous_text, validate_edit_path

_DIFF_HEADER = re.compile(r"^diff --git a/(.+) b/(.+)$")


class PatchValidationError(RuntimeError):
    """Raised when a patch cannot be parsed or validated."""


def _normalize_diff_path(raw_path: str) -> str | None:
    raw_path = raw_path.strip()
    if raw_path == "/dev/null":
        return None
    if raw_path.startswith("a/") or raw_path.startswith("b/"):
        return raw_path[2:]
    return raw_path


def parse_unified_diff(patch_text: str) -> list[PatchChange]:
    changes: list[PatchChange] = []
    current: PatchChange | None = None

    for raw_line in patch_text.splitlines():
        header_match = _DIFF_HEADER.match(raw_line)
        if header_match:
            current = PatchChange(
                path=header_match.group(2),
                old_path=header_match.group(1),
                new_path=header_match.group(2),
            )
            changes.append(current)
            continue

        if current is None:
            continue

        if raw_line.startswith("new file mode "):
            current.is_new = True
            continue
        if raw_line.startswith("deleted file mode "):
            current.is_deleted = True
            continue
        if raw_line.startswith("--- "):
            current.old_path = _normalize_diff_path(raw_line[4:])
            continue
        if raw_line.startswith("+++ "):
            current.new_path = _normalize_diff_path(raw_line[4:])
            current.path = current.new_path or current.old_path or current.path
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            current.added_lines.append(raw_line[1:])
            continue
        if raw_line.startswith("-") and not raw_line.startswith("---"):
            current.removed_lines.append(raw_line[1:])
            continue

    return changes


def _is_test_path(path: str) -> bool:
    pure = Path(path)
    return bool(pure.parts) and pure.parts[0] == "tests"


def validate_patch_text(
    patch_text: str, *, repo_root: Path, config: Config
) -> PatchValidationResult:
    errors: list[str] = []
    retryable_invalid_diff = False

    if config.patch.require_unified_diff and "diff --git " not in patch_text:
        errors.append("Patch is not a unified diff.")
        retryable_invalid_diff = True

    lower_patch = patch_text.lower()
    if "git binary patch" in lower_patch or "binary files " in lower_patch:
        errors.append("Binary patches are not allowed.")
    if "old mode " in patch_text or "\nnew mode " in patch_text:
        errors.append("Mode changes are not allowed.")
    if "rename from " in patch_text or "rename to " in patch_text:
        errors.append("Rename patches are not allowed.")

    changes = parse_unified_diff(patch_text)
    if not changes:
        errors.append("Patch does not contain any file changes.")
        retryable_invalid_diff = True

    files_changed: list[str] = []
    new_files: list[str] = []
    deleted_files: list[str] = []

    if len(changes) > config.patch.max_files_changed:
        errors.append(
            f"Patch touches {len(changes)} files, above max_files_changed={config.patch.max_files_changed}."
        )

    for change in changes:
        target_path = change.new_path or change.old_path or change.path
        if target_path is None:
            errors.append("Patch contains an empty path.")
            continue
        try:
            validate_edit_path(repo_root, config, target_path)
        except SafetyError as exc:
            errors.append(str(exc))
            continue

        files_changed.append(target_path)

        if change.is_deleted:
            deleted_files.append(target_path)
            errors.append(f"Deleting files is not allowed in Phase 2: {target_path}")
            continue

        patch_target = repo_root / target_path
        if change.is_new:
            new_files.append(target_path)
            if _is_test_path(target_path):
                if not config.patch.allow_new_tests:
                    errors.append(f"Creating new test files is blocked: {target_path}")
            elif not config.patch.allow_new_source_files:
                errors.append(f"Creating new source files is blocked: {target_path}")
        elif not patch_target.exists():
            errors.append(f"Patch modifies a file that does not exist: {target_path}")

        snippet = contains_dangerous_text("\n".join(change.added_lines))
        if snippet:
            errors.append(f"Patch adds dangerous content ({snippet}) in {target_path}")

    return PatchValidationResult(
        valid=not errors,
        retryable_invalid_diff=retryable_invalid_diff
        and not any(
            error.startswith("Editing ")
            or error.startswith("Creating new ")
            or error.startswith("Deleting files ")
            or error.startswith("Patch modifies a file ")
            or "dangerous content" in error
            or "Binary patches" in error
            or "Mode changes" in error
            or "Rename patches" in error
            for error in errors
        ),
        errors=errors,
        files_changed=files_changed,
        new_files=new_files,
        deleted_files=deleted_files,
        patch_changes=changes,
    )

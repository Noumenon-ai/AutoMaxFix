from __future__ import annotations

import json

from .models import Config, RepoContext, StrategyName, Ticket


def _render_repo_context(repo_context: RepoContext) -> str:
    repo_entries = "\n".join(f"- {item}" for item in repo_context.top_level_entries) or "- none"
    suspected = "\n".join(f"- {item['path']}" for item in repo_context.suspected_files) or "- unknown"
    return f"Repo snapshot:\n{repo_entries}\n\nSuspected files:\n{suspected}"


def _render_base_prompt(
    *,
    ticket: Ticket,
    repo_context: RepoContext,
    config: Config,
    reproduction_test: str | None,
    attempt_number: int,
    validation_errors: list[str] | None,
) -> str:
    ticket_json = json.dumps(ticket.to_dict(), indent=2, sort_keys=False)
    allowed_paths = "\n".join(f"- {item}" for item in config.allowed_paths)
    blocked_paths = "\n".join(f"- {item}" for item in config.blocked_paths)
    retry_block = ""
    if validation_errors:
        rendered_errors = "\n".join(f"- {item}" for item in validation_errors)
        retry_block = (
            "Previous output failed unified diff validation.\n"
            "Fix these exact problems and return a corrected unified diff only:\n"
            f"{rendered_errors}\n\n"
        )
    return (
        f"AutoMaxFix Ticket Repair Attempt {attempt_number}\n\n"
        f"{retry_block}"
        "Ticket JSON:\n"
        f"{ticket_json}\n\n"
        "Repo rules:\n"
        f"- repo_path: {config.repo_path}\n"
        f"- allowed paths:\n{allowed_paths}\n"
        f"- blocked paths:\n{blocked_paths}\n\n"
        "Safety rules:\n"
        "- One ticket only.\n"
        "- Never bypass reproduction requirement.\n"
        "- Never touch .git, .env, secrets, .venv, or node_modules.\n"
        "- Never install packages.\n"
        "- Never use network commands.\n"
        "- Never produce markdown fences or explanations.\n"
        "- Output a unified diff only.\n\n"
        "Required reproduction test:\n"
        f"- {reproduction_test or 'none provided'}\n\n"
        f"{_render_repo_context(repo_context)}\n"
    )


def _render_strategy_directive(strategy: StrategyName) -> str:
    if strategy == StrategyName.MINIMAL:
        return "Aim for the minimal diff."
    if strategy == StrategyName.TEST_FIRST:
        return "Rewrite the failing test to clearly express the expected behavior, then write the implementation."
    if strategy == StrategyName.REFACTOR:
        return "A focused refactor is allowed if it clarifies the fix or reduces risk."
    return "Prefer rolling back the suspected recent change first, then make the smallest follow-up needed."


def build_codex_prompt(
    *,
    ticket: Ticket,
    repo_context: RepoContext,
    config: Config,
    reproduction_test: str | None,
    attempt_number: int,
    validation_errors: list[str] | None,
    strategy: StrategyName = StrategyName.MINIMAL,
) -> str:
    return (
        _render_base_prompt(
            ticket=ticket,
            repo_context=repo_context,
            config=config,
            reproduction_test=reproduction_test,
            attempt_number=attempt_number,
            validation_errors=validation_errors,
        )
        + "\nCodex preset:\n"
        + "- Start the first line with diff --git.\n"
        + f"- Strategy: {strategy.value}.\n"
        + f"- {_render_strategy_directive(strategy)}\n"
        + "- Keep the patch scoped to the ticket.\n"
        + "- Prefer editing existing files over creating new source files.\n"
        + "- If a new file is necessary, only create a test file under tests/.\n"
    )


def build_claude_prompt(
    *,
    ticket: Ticket,
    repo_context: RepoContext,
    config: Config,
    reproduction_test: str | None,
    attempt_number: int,
    validation_errors: list[str] | None,
    strategy: StrategyName = StrategyName.MINIMAL,
) -> str:
    return (
        _render_base_prompt(
            ticket=ticket,
            repo_context=repo_context,
            config=config,
            reproduction_test=reproduction_test,
            attempt_number=attempt_number,
            validation_errors=validation_errors,
        )
        + "\nClaude preset:\n"
        + "- Return only a unified diff with no commentary.\n"
        + f"- Strategy: {strategy.value}.\n"
        + f"- {_render_strategy_directive(strategy)}\n"
        + "- Ensure every changed file has matching --- and +++ headers.\n"
        + "- Keep the patch narrowly targeted to the failing reproduction.\n"
        + "- Prefer modifying existing files over adding new source files.\n"
    )

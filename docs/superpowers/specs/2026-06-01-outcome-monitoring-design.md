# Outcome Monitoring — `automaxfix monitor` (roadmap #1)

Status: approved design (2026-06-01). Build target for Codex. TDD required.
Branch: `feat/outcome-monitoring`.

## Why
After a fix is verified, nothing today re-checks that it keeps holding. Outcome
monitoring re-runs the exact verification that proved a fix and raises a fresh
ticket if the failure returns. This is the front-half of the roadmap loop
("monitor outcome"), built on existing primitives only.

## Grounding (already in the codebase — reuse, do not reinvent)
- A successfully-fixed ticket has `status == "passed"` (set in cli.py) and
  persists `verification_command` (and `reproduction_command`) on the Ticket
  dataclass (models.py). Check-sourced tickets already carry their check command
  there; test-sourced tickets carry the targeted test command.
- The sanitized minimal-env subprocess runner is `run_command(..., allow_full_env=False)`
  in `automaxfix/utils.py` (from PR #11). Use it for re-verification.
- Tickets are loaded/saved via `automaxfix/ticket.py` (`load_ticket`, `save_ticket`,
  `next_ticket_id`, `resolve_tickets_dir`, `create_ticket_from_failures`). Tickets
  carry an integrity sha256 (reliability.py) — go through the existing helpers,
  do not hand-write ticket files.

## Behavior
- **`find_monitorable(tickets) -> list[Ticket]`** (new `automaxfix/monitor.py`):
  tickets with `status == "passed"` AND a non-empty `verification_command`.
- **`monitor_once(tickets, repo_root, *, now=None) -> list[MonitorResult]`**:
  for each monitorable ticket, re-run its `verification_command` via
  `run_command(..., allow_full_env=False, timeout_seconds=<config subprocess timeout>)`.
  A ticket has **regressed** when the verification now FAILS:
  - default/plain verify command → non-zero exit is a regression.
  - (Keep it simple: re-run the stored verification_command and treat non-zero
    exit as failure. Do NOT re-derive check matches/not_matches semantics here —
    the stored command is what proved the fix; its own exit code is the signal.)
  Return a result per ticket: `{ticket_id, regressed: bool, returncode, output_excerpt}`.
- **Regression handling (user-approved): NEW LINKED TICKET.** For each regression,
  create a fresh ticket via the existing ticket helpers with:
  - `source = "regression"`
  - `regressed_from = <original ticket id>` (new optional field — see below)
  - `verification_command` and `reproduction_command` copied from the original
  - `suspected_files` copied from the original
  - title/bug_report noting it previously passed and the verification now fails,
    with the captured output excerpt.
  Do NOT mutate the original ticket's status.

## Model change (small)
Add optional `regressed_from: str | None = None` to the `Ticket` dataclass
(models.py): include in `to_dict` and `from_dict` (round-trip, default None for
old tickets). This seeds the future reliability-ledger/provenance. No other model
changes.

## CLI
New subcommand `automaxfix monitor [--since-days N]`:
- loads all tickets, `find_monitorable`, `monitor_once`, writes a regression
  ticket per regression, prints a summary (N monitored, M regressed, new ticket
  ids). `--since-days N` (optional) limits to tickets whose last activity /
  created_at is within N days. One-shot — NO scheduler/daemon.

## Tests (TDD — write first, meaningful, no weakening)
- `tests/test_monitor.py`:
  - passed ticket whose verify command still exits 0 → no regression.
  - passed ticket whose verify command now exits non-zero → exactly one regression
    result, and `monitor_once`/the CLI creates ONE new ticket with
    `source=="regression"`, `regressed_from==<original id>`, and the same
    `verification_command`.
  - ticket with status != "passed" → skipped.
  - passed ticket with empty/None `verification_command` → skipped.
  - `--since-days` window filters correctly (use injected `now`, do NOT call
    datetime.now() inside tests — pass a fixed timestamp).
  - re-verification subprocess uses the sanitized minimal env (plant a secret in
    os.environ, assert the verify command cannot see it) — mirror the #11 / checks
    env test.
  - `Ticket.regressed_from` round-trips through to_dict/from_dict.
- CLI test: `automaxfix monitor` with one regressed passed-ticket fixture writes a
  valid regression ticket and exits cleanly.
- Keep the existing 101 tests green. black + ruff clean.

## OUT OF SCOPE (do not build)
- No daemon/scheduler/cron (scheduling is external; one-shot command only).
- No auto-fixing inside monitor (it detects + tickets only; the normal run flow
  fixes the regression ticket).
- No notifications (Telegram/Discord/email).
- No changes to run/scan/check/watch behavior, scanners, or the safety pipeline.
- No re-deriving check matches/not_matches logic in monitor — re-run the stored
  command and use its exit code.

## Constraints
- 100% real, runnable code. No stubs, mocks-as-product, demo modes, TODOs.
- Branch `feat/outcome-monitoring` ONLY. Commit on green (no push).
- NO emojis anywhere (code, comments, commit messages, output).
- NO "Generated with Claude" / "Co-Authored-By: Claude" trailers.
- COMPLETION: when the full suite passes, `git commit` locally and report the
  commit hash + one-line summary + final test count. Do not finish silently.

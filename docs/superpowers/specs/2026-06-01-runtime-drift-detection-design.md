# Runtime-Drift Detection Layer — Check Scanner (v1)

Status: approved design (2026-06-01). Build target for Codex. TDD required.

## Why
Today AMF only detects failures that a **test runner** prints (pytest/jest/…).
It is structurally blind to *runtime drift*: a service that died, a healthcheck
that went red, an error line that appeared in a log, a stale config that
crash-loops. This adds the first detection beyond test output, advancing the
"reliability layer" thesis. The repositioning README/ROADMAP is a SEPARATE,
later step — **this build is code only.**

## The one primitive (do NOT generalize beyond this)
A **command check**: run a command, judge pass/fail. This single mechanism
covers healthchecks (`curl -f`), service state (`systemctl is-active X`), log
patterns (`! grep -q ERROR app.log`), process liveness, etc. We do **NOT**
build separate log/HTTP/systemd/remote detectors — they are all just commands.

## Architecture (reuse existing pipeline — invent no new flow)
```
checks config → run_checks() → FailureRecord(s) → create_ticket_from_failures(source="check") → existing reproduce→fix→validate→report
```

### Files
- **NEW `automaxfix/checks.py`**
  - `@dataclass CheckDefinition`: `name: str`, `command: str`,
    `expect: str = "exit_zero"` (one of `exit_zero` | `matches` | `not_matches`),
    `pattern: str | None = None` (regex, required when expect is matches/not_matches),
    `suspected_files: list[str] = []`, `severity: int = 2`,
    `timeout_seconds: int = 60`.
  - `run_checks(checks: list[CheckDefinition], repo_root: Path) -> list[FailureRecord]`:
    runs each check; on **failure** appends
    `FailureRecord(test_id=name, error_summary=<concise reason e.g. "exit 3" or "matched /ERROR/">, raw_excerpt=<combined stdout+stderr, truncated to ~2000 chars>, file_path=<first suspected_files entry or None>, line=None)`.
    Pass conditions: `exit_zero` → returncode 0; `matches` → regex found in output → that is a FAILURE (e.g. error pattern present); `not_matches` → regex absent → FAILURE if absent? **Define precisely in spec below.**
  - Failure semantics (be explicit, test all three):
    - `exit_zero`: FAIL when returncode != 0.
    - `matches`: FAIL when `pattern` IS found in combined output (use for "an error string appeared").
    - `not_matches`: FAIL when `pattern` is NOT found (use for "the healthy marker is missing").
  - Subprocess: reuse the **sanitized/minimal-env runner added in #11** (`automaxfix/utils.py`) — do NOT pass full `os.environ`. Enforce `timeout_seconds`; a timeout is a FAIL with reason "timeout after Ns". Capture stdout+stderr.
- **MODIFY `automaxfix/config.py`**: parse an optional top-level `checks:` list in `.automaxfix/config.yml` into `list[CheckDefinition]`. Absent/empty → `[]`. Validate: each needs `name`+`command`; matches/not_matches need `pattern` (raise a clear config error otherwise). Add to `Config.to_dict`/`from_dict` round-trip + `init` template gets a commented-out example check.
- **MODIFY `automaxfix/cli.py`**: new subcommand `automaxfix check` →
  loads config, `run_checks(config.checks, repo_root)`, then for each failure
  create a ticket via the **existing** `create_ticket_from_failures` (or
  `create_bug_ticket`) with `source="check"`, so the check **command becomes the
  ticket's reproduction/verification command** (re-running the SAME check
  validates any future fix — it can't be satisfied by editing a test). Print a
  summary; support the same output format flag(s) as `scan` where trivial.
  Writes ticket JSON to the existing tickets dir.

## Honesty boundary (REQUIRED — this is the point of the tool)
When a check's root cause is outside the repo path allowlist (e.g. `/etc/...`),
AMF **detects + tickets + reports, then stops** — the existing path-allowlist
already blocks out-of-repo edits, so no new enforcement code is needed, but the
`check` command output and ticket `bug_report` must state plainly that the fix
may be outside the repo and require a human. **No pretense of auto-fixing it.**

## Tests (TDD — write first, must be meaningful, no weakening)
- `tests/test_checks.py`:
  - exit_zero: passing command → no FailureRecord; failing (exit!=0) → one FailureRecord with correct fields.
  - matches: pattern present → FAIL; absent → pass.
  - not_matches: pattern absent → FAIL; present → pass.
  - output capture + truncation (>2000 chars truncated, marker added).
  - timeout → FAIL with timeout reason.
  - missing `pattern` for matches/not_matches → clear config/validation error.
  - subprocess env is the sanitized/minimal env (assert a sentinel secret in os.environ is NOT visible to the check) — mirrors #11 tests.
- `tests/test_cli.py` (or test_cli_scan_formats.py style): `automaxfix check`
  with one failing configured check produces a valid ticket JSON whose
  reproduction/verify command equals the check command, `source=="check"`.
- Keep the existing 87 tests green. Black + ruff clean.

## OUT OF SCOPE (do not build — prevents drift)
- No watch-mode auto-invocation of checks (watch can call `check` later — roadmap).
- No scheduler/daemon, no remote/HTTP/log-specific detector classes (command covers all).
- No README rewrite / ROADMAP / repositioning (separate reviewed step).
- No new auto-fix logic for out-of-repo causes.
- No changes to existing scanners or the patch/safety pipeline.

## Constraints
- 100% real, runnable code. No stubs, mocks-as-product, demo modes, TODOs.
- Work ONLY on branch `feat/runtime-drift-detection`. **Do NOT push.**
- Commits: NO "Generated with Claude" / "Co-Authored-By: Claude" trailers.
- Follow existing code style, typing, and the scanner/ticket patterns already in the repo.

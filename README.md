# AutoMaxFix

> A reliability layer for AI-built systems. AutoMaxFix watches for failures,
> reproduces them, repairs them one ticket at a time behind a human approval
> gate, and proves the fix before it is trusted. It is deliberately the boring
> opposite of an autonomous agent: one ticket, one patch attempt, one approval,
> one report. Then it stops.

[![CI](https://github.com/Noumenon-ai/AutoMaxFix/actions/workflows/ci.yml/badge.svg)](https://github.com/Noumenon-ai/AutoMaxFix/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

The valuable part of an AI coding system is not "AI writes code" — everyone has
that. The hard, rarer part is knowing *when code is broken, proving it, proving
the fix, and preventing regressions*. AutoMaxFix is built around that: a
command-line reliability tool for AI-built projects that turns failures into
structured tickets, drives a local agent CLI through a strict patch contract,
and validates every repair against the same signal that detected the problem.

## Works today vs. on the roadmap

This split is deliberate and honest. Everything in the left column is shipped,
tested, and covered by the suite. The right column is direction, not done.

| Works today | On the roadmap |
| --- | --- |
| Detect failures from test runners (pytest, jest, vitest, mocha, go, cargo, generic) | Anomaly detection beyond explicit checks (metrics, traces, statistical drift) |
| Detect **runtime drift** via command checks — healthchecks, service state, log patterns, process liveness | A cross-run reliability ledger / fix provenance trusted across agents |
| **Outcome monitoring** — re-verify passed fixes (`automaxfix monitor`) and raise a linked regression ticket when a fix stops holding | Learning from past fixes to prioritize and pre-empt failures |
| Reproduce, repair one ticket at a time, validate with targeted + regression tests | Scheduled/continuous monitoring as a managed loop (today `monitor` is one-shot, run via cron or `watch`) |
| Human approval gate; one ticket then stop; optional watch loop on an interval | Repair beyond the repo (config/infra) — today these are detected and reported, not auto-patched |
| Hardened: path allowlist, command/secret blocks, sanitized agent env, **all existing-test edits blocked** (a fix can't weaken the tests it must satisfy, even in `--no-repro` mode), ticket integrity checksums | |

See [ROADMAP.md](ROADMAP.md) for the longer-term loop and where the project is headed.

## Install

Python 3.11+.

```
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/automaxfix --help
```

## Quickstart

```
automaxfix init
pytest -q 2>&1 | tee pytest.log || true
automaxfix scan --pytest-output pytest.log
automaxfix run --ticket .automaxfix/tickets/AMF-YYYYMMDD-001.json --agent codex_cli
```

`run` validates the diff, asks for approval (unless `--yes`), applies the patch
inside the path allowlist, runs the targeted and regression tests (plus, for
check-sourced tickets, the originating check), and writes a report. It stops
after one ticket.

## What it does

- Parses pytest, jest, vitest, mocha, go test, cargo test, and generic test
  runner output into structured tickets.
- Detects **runtime drift** from command checks — not just test output (see
  [Checks](#checks-runtime-drift-detection)).
- Generates a reproduction brief per ticket.
- Drives Codex CLI or Claude CLI through a strict prompt/diff contract.
- Validates every diff against the safety rules below before apply.
- Runs targeted and regression tests after apply; check-sourced tickets must
  also pass a re-run of the originating check.
- Writes a per-run report with rollback instructions.

## Checks (runtime-drift detection)

Test runners only surface failures that a test prints. A lot of real breakage —
a service that died, a healthcheck gone red, an error line in a log, a stale
config that crash-loops — never shows up as a failing test. A **check** closes
that gap with one primitive: run a command, judge pass/fail.

Define checks in `.automaxfix/config.yml`:

```
checks:
  - name: 'nexus service up'
    command: 'systemctl --user is-active nexus.service'
    expect: 'exit_zero'          # FAIL when the command exits non-zero
  - name: 'healthy marker present'
    command: 'cat app.log'
    expect: 'not_matches'        # FAIL when the pattern is MISSING
    pattern: 'started cleanly'
  - name: 'error appeared in log'
    command: 'cat app.log'
    expect: 'matches'            # FAIL when the pattern IS present
    pattern: 'ERROR'
```

Failure semantics: `exit_zero` fails on a non-zero exit; `matches` fails when
the pattern is found (use it for "an error string appeared"); `not_matches`
fails when the pattern is missing (use it for "the healthy marker is gone").
Then:

```
automaxfix check
```

runs every configured check and files a ticket for each failure. A check-sourced
ticket carries the check command as its reproduction and verification step, so a
proposed fix is validated by re-running the exact check that caught the failure —
it cannot be satisfied by editing a test. Checks run with a minimal sanitized
environment; your `os.environ` is never exposed to the command.

When a failure's root cause is outside the repository (for example a
`/etc/systemd` unit), AutoMaxFix detects, tickets, and reports it — it does not
pretend it can patch something outside its allowlist.

## Outcome monitoring

A fix that passed once can quietly break later. `automaxfix monitor` re-runs the
verification of every previously-passed ticket and raises a fresh ticket if the
failure has returned:

```
automaxfix monitor [--since-days N]
```

For each ticket with status `passed` and a stored verification command, monitor
re-runs the original signal in the sanitized minimal environment: check-sourced
tickets re-apply the full check semantics (exit code plus `matches` /
`not_matches` pattern), other tickets re-run the stored verification command and
judge by exit code. If the signal now fails,
monitor creates a new **regression ticket** (`source: regression`,
`regressed_from: <original id>`) that copies the original's verification,
reproduction, and suspected files, then flows into the normal repair loop. The
original ticket is left untouched, so the history of "fixed, then regressed" is
preserved.

It re-uses the same signal that originally proved the fix, so a regression cannot
be hidden by editing a test. `monitor` is one-shot by design — schedule it with
cron or alongside `watch`; there is no background daemon. `--since-days N` limits
monitoring to tickets created within the last N days.

## What it does not do

- Does not call any hosted API directly. It drives whichever local agent CLI is
  configured.
- Does not run unattended without `--yes`. Approval is the default.
- Does not chain tickets. One ticket per run.
- Does not auto-repair causes outside the repo allowlist. It reports them.
- Does not install packages, run `curl | bash`, or run anything outside the
  safety rules.

## Configuration

`.automaxfix/config.yml` is created by `automaxfix init`, which also adds
`.automaxfix/` to your `.gitignore`. Key fields:

```
agent:
  mode: "codex_cli"          # codex_cli | claude_cli | manual_patch_file
  command: "codex"
repo_path: "."
allowed_paths: ["src", "tests"]
blocked_paths: [".git", ".env*", "secrets*", ".venv", "node_modules"]
max_files_changed: 8
patch:
  max_patch_attempts: 3
watch_mode:
  default_interval: 30
  auto_approve_in_watch: false
subprocess_timeout_seconds: 300
checks: []                   # optional runtime-drift checks (see above)
```

## CLI

```
automaxfix init
automaxfix scan --pytest-output FILE
automaxfix scan --jest-output FILE
automaxfix scan --vitest-output FILE
automaxfix scan --mocha-output FILE
automaxfix scan --go-output FILE
automaxfix scan --cargo-output FILE
automaxfix scan --from-file FILE --format generic
automaxfix check
automaxfix bug "free-text bug report"
automaxfix reproduce --ticket PATH
automaxfix run --ticket PATH [--patch-file FILE] [--agent codex_cli|claude_cli] [--yes] [--max-attempts N] [--no-repro]
automaxfix watch --test-runner pytest --command "pytest -q" [--interval SECONDS]
automaxfix monitor [--since-days N]
automaxfix report [--latest]
automaxfix status
automaxfix metrics [--since-days N] [--format text|json]
automaxfix backup [--output-dir PATH]
```

## Safety

The safety floor is enforced before any agent sees a prompt:

- Edits cannot leave `repo_path` or enter `blocked_paths`.
- Diffs that touch `.git`, `.env*`, `secrets*`, `.venv`, `node_modules`, or any
  other configured blocked path are rejected at validation time.
- A fix patch cannot modify or delete ANY pre-existing test file — not just the
  reproduction, and including in `--no-repro` mode where no single reproduction is
  designated. A fix must change the code, never weaken the tests it is validated
  against (`block_test_edits`, on by default; new tests still allowed).
- Package installs, `curl | bash`, `wget | bash`, `sudo`, and `rm -rf` patterns
  are rejected (tokenized, not naive substring matching).
- Binary patches, mode-change-only patches, and patches that exceed
  `max_files_changed` are rejected.
- Workspace must be clean (no uncommitted changes) before apply. AutoMaxFix's
  own state files under `.automaxfix/` are excluded from that check, and
  `automaxfix init` adds `.automaxfix/` to your `.gitignore`.
- Agent and check subprocesses run with a minimal sanitized environment, so the
  full `os.environ` is never exposed.
- Ticket content is sanitized before write: tokens, keys, and other
  credential-shaped strings are replaced with `[REDACTED]`.
- Ticket files carry an integrity sha256 verified on load: a ticket whose
  checksum no longer matches its content is refused with an error. Legacy
  tickets without a checksum field still load.

`automaxfix backup` archives `.automaxfix/` to a timestamped tarball so the local
ticket archive survives accidental deletion.

## CI

A GitHub Actions composite action wraps the CLI for failure-driven runs. See
`.github/actions/automaxfix-action/README.md`. The example wires into the
`tests` workflow as:

```yaml
- name: Run tests
  run: pytest -q 2>&1 | tee pytest-failures.log
- name: AutoMaxFix on failure
  if: failure()
  uses: ./.github/actions/automaxfix-action
  with:
    test-runner: pytest
    test-output-path: pytest-failures.log
    agent: codex_cli
    require-approval: true
    open-pr: true
```

## Rollback

Every apply writes a pre-patch diff to
`.automaxfix/reports/pre_patch_<ticket>.diff` and the applied diff to
`.automaxfix/logs/applied_<ticket>.diff`. To revert:

```
git apply -R .automaxfix/logs/applied_<ticket>.diff
```

## License

MIT. See `LICENSE`.

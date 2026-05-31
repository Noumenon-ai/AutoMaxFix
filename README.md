# AutoMaxFix

> AutoMaxFix is the boring opposite of an autonomous agent. One ticket, one patch attempt, one approval, one report. Then it stops.

[![CI](https://github.com/Noumenon-ai/AutoMaxFix/actions/workflows/ci.yml/badge.svg)](https://github.com/Noumenon-ai/AutoMaxFix/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

AutoMaxFix is a command-line tool for controlled patch repair in
AI-built projects. It reads test runner output, creates structured
tickets, and runs agent-driven repair one ticket at a time with a
human approval gate.

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

`run` validates the diff, asks for approval (unless `--yes`), applies
the patch inside the path allowlist, runs the targeted and regression
tests, and writes a report. It stops after one ticket.

## What it does

- Parses pytest, jest, vitest, mocha, go test, cargo test, and generic
  test runner output into structured tickets.
- Generates a reproduction brief per ticket.
- Drives Codex CLI or Claude CLI through a strict prompt/diff contract.
- Validates every diff against the safety rules below before apply.
- Runs targeted and regression tests after apply.
- Writes a per-run report with rollback instructions.

## What it does not do

- Does not call any hosted API directly. It drives whichever local
  agent CLI is configured.
- Does not run unattended without `--yes`. Approval is the default.
- Does not chain tickets. One ticket per run.
- Does not install packages, run `curl | bash`, or run anything outside
  the safety rules.

## Configuration

`.automaxfix/config.yaml` is created by `automaxfix init`. Key fields:

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
automaxfix bug "free-text bug report"
automaxfix reproduce --ticket PATH
automaxfix run --ticket PATH [--patch-file FILE] [--agent codex_cli|claude_cli] [--yes] [--max-attempts N] [--no-repro]
automaxfix watch --test-runner pytest --command "pytest -q" [--interval SECONDS]
automaxfix report [--latest]
automaxfix status
automaxfix metrics [--since-days N] [--format text|json]
automaxfix backup [--output-dir PATH]
```

## Safety

The safety floor is enforced before any agent sees a prompt:

- Edits cannot leave `repo_path` or enter `blocked_paths`.
- Diffs that touch `.git`, `.env*`, `secrets*`, `.venv`, `node_modules`,
  or any other configured blocked path are rejected at validation time.
- Package installs, `curl | bash`, `wget | bash`, `sudo`, and `rm -rf`
  patterns are rejected.
- Binary patches, mode-change-only patches, and patches that exceed
  `max_files_changed` are rejected.
- Workspace must be clean (no uncommitted changes) before apply.
- Ticket content is sanitized before write: tokens, keys, and other
  credential-shaped strings are replaced with `[REDACTED]`.
- Ticket files carry an integrity sha256 verified on load.

`automaxfix backup` archives `.automaxfix/` to a timestamped tarball so
the local ticket archive survives accidental deletion.

## CI

A GitHub Actions composite action wraps the CLI for failure-driven runs.
See `.github/actions/automaxfix-action/README.md`. The example wires
into `tests` workflow as:

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

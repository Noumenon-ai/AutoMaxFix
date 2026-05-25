# AutoMaxFix CI Integration

AutoMaxFix ships two GitHub Actions entrypoints:

- `./.github/actions/automaxfix-action`: a composite action for same-job use after a failing test step has already written a log file.
- `./.github/workflows/automaxfix-on-fail.yml`: a reusable workflow wrapper that downloads the failure log artifact, runs the composite action, uploads the report artifact, comments on the PR or issue, and either opens a PR or pushes direct.

The reusable workflow is the better default for CI because it keeps reporting and publish logic in one place.

## Typical GitHub Actions Wiring

Use a test job to capture the failure log and upload it as an artifact only when tests fail. Then call the reusable workflow in a second job.

```yaml
name: ci

on:
  pull_request:
    types: [opened, synchronize, reopened, labeled]
  issue_comment:
    types: [created]

jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Run pytest
        run: pytest -q 2>&1 | tee pytest-failures.log
      - name: Upload failure log
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: pytest-failures
          path: pytest-failures.log

  automaxfix:
    needs: tests
    if: ${{ needs.tests.result == 'failure' }}
    uses: ./.github/workflows/automaxfix-on-fail.yml
    with:
      test-runner: pytest
      test-output-path: pytest-failures.log
      test-output-artifact: pytest-failures
      agent: codex_cli
      require-approval: true
      open-pr: true
```

If you do not need the reusable workflow wrapper, call the composite action directly in the same job right after the failing test step. That is the simplest path when the log file already exists in the workspace.

## Runner Examples

### Pytest

```yaml
- name: Run pytest
  run: pytest -q 2>&1 | tee pytest-failures.log
- name: AutoMaxFix
  if: failure()
  uses: ./.github/actions/automaxfix-action
  with:
    test-runner: pytest
    test-output-path: pytest-failures.log
    agent: codex_cli
    require-approval: true
```

### Jest

```yaml
- name: Run Jest
  run: npx jest --runInBand 2>&1 | tee jest-failures.log
- name: AutoMaxFix
  if: failure()
  uses: ./.github/actions/automaxfix-action
  with:
    test-runner: jest
    test-output-path: jest-failures.log
    agent: claude_cli
    require-approval: true
```

### Go

```yaml
- name: Run go test
  run: go test ./... 2>&1 | tee go-test-failures.log
- name: AutoMaxFix
  if: failure()
  uses: ./.github/actions/automaxfix-action
  with:
    test-runner: go
    test-output-path: go-test-failures.log
    agent: codex_cli
    require-approval: true
```

## Agent Prerequisites

- `codex_cli` expects a `codex` executable to already exist on the runner, or a custom command in your checked-in `.automaxfix/config.yml`.
- `claude_cli` expects a `claude` executable on the runner, or a custom command in your config.
- `manual_patch_file` is only useful when the workflow sets `AUTOMAXFIX_PATCH_FILE` to a real unified diff path.
- The composite action installs `automaxfix` from PyPI by default. For a self-hosted checkout, pass `install-target: .` so it uses `pip install -e .`.

## Scoping `allowed_paths`

Treat the path allowlist as mandatory in CI. Keep the patch surface narrow and leave `.github`, deployment code, and secrets-bearing directories out unless you are intentionally letting AutoMaxFix touch them.

```yaml
repo_path: "."
allowed_paths:
  - "src"
  - "tests"
blocked_paths:
  - ".github"
  - "infra"
  - ".venv"
patch:
  max_files_changed: 4
approval:
  require_human_approval: true
```

The CI safety floor should be:

- `allowed_paths` locked to source and test directories you are comfortable patching
- the dirty workspace check left enabled by running against a clean checkout
- `patch.max_files_changed` capped to a small number

That combination prevents most accidental patch sprawl before any PR is opened or branch is pushed.

## Approval Gating In CI

`ci_mode: true` makes AutoMaxFix default `require_human_approval` to `false`, which is useful for unattended runners. The reusable workflow deliberately puts the safer behavior back in front:

- `require-approval: true` means the first CI run stops at the approval gate and comments on the PR or issue with the report link.
- Adding the `automaxfix-approved` label or commenting `/automaxfix approve` lets the reusable workflow drop the gate on the next run.
- When the gate is lifted, the workflow reruns AutoMaxFix, applies the patch, uploads the report, and either opens a PR or pushes direct depending on `open-pr`.

If you want fully unattended fixing in a protected sandbox, set `require-approval: false`. Do that only after you have a tight allowlist and a small `max_files_changed` cap.

## Security And Permissions

The reusable workflow needs:

- `contents: write` so it can push a branch or update the checked-out branch when `open-pr: false`
- `pull-requests: write` so it can open or update the AutoMaxFix PR

If you want AutoMaxFix to comment on issues as well as PRs, add `issues: write` for the comment step.

The blast radius is straightforward: the workflow token can publish whatever file edits AutoMaxFix makes inside the checked-out repository. That is why the minimum guardrails in CI should be a narrow `allowed_paths` list, a clean checkout, and a low `max_files_changed` cap. Do not give the workflow a broader token or a broader patch surface than you are willing to let a bot branch modify.

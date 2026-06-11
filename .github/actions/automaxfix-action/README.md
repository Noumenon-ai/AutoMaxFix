# AutoMaxFix CI Action

A composite GitHub Action that runs AutoMaxFix against a captured failing
test log inside a workflow. It installs AutoMaxFix, builds a CI config
overlay from your `.automaxfix/config.yml`, scans the failure log into a
ticket, and runs the repair loop for that one ticket. See
[action.yml](action.yml) for the authoritative definition.

## Usage

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

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `test-runner` | yes | | `pytest`, `jest`, `vitest`, `mocha`, `go`, `cargo`, or `generic` |
| `test-output-path` | yes | | Path to the captured failure log in the workflow workspace |
| `agent` | no | `codex_cli` | `codex_cli`, `claude_cli`, or `manual_patch_file` |
| `require-approval` | no | `"true"` | Keep the human approval gate; the run stops at `approval_required` instead of applying |
| `open-pr` | no | `"true"` | Hint for the calling workflow to open a PR instead of pushing directly |
| `install-target` | no | `automaxfix` | PyPI package name or a local path for editable installs |

With `agent: manual_patch_file`, set the `AUTOMAXFIX_PATCH_FILE` environment
variable to the unified diff to apply.

## Outputs

| Output | Description |
| --- | --- |
| `outcome` | `success`, `approval_required`, or `failure` |
| `ticket-id` | The AutoMaxFix ticket ID selected for the run |
| `ticket-path` | The saved ticket JSON path |
| `report-path` | The generated report path |
| `patch-artifact-path` | The saved applied-patch artifact path |
| `patch-summary` | Patch summary or approval message from the ticket |
| `error-message` | Error summary for failed runs |
| `run-url` | GitHub Actions run URL for traceability |

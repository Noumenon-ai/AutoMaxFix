# ADR 001: One ticket per run

Status: Accepted
Date: 2026-05-26

## Context

AutoMaxFix repairs bugs by running an agent against a single failure at a
time. Early prototypes attempted batch repair (multi-failure prompt). Three
failure modes appeared:

1. Cross-ticket contamination: the agent applied a patch for one ticket
   that broke an unrelated ticket scheduled later in the batch.
2. Unclear approval state: a batch could be partially approved, leaving
   half-applied diffs on disk with no rollback path.
3. Inscrutable reports: a batch produced one report summarizing five
   different reasoning chains. Debugging required reconstructing which
   change traced to which failure.

## Decision

Each run repairs exactly one ticket. The CLI does not accept multi-ticket
arguments. Batch behavior, if needed, is provided by a thin shell loop
around the single-run command, not by the core binary.

## Consequences

- Reports are 1:1 with a ticket id, which lets users grep by ticket id.
- Approval gates apply to one change set at a time.
- The batch use case requires a wrapper. This is acceptable: the wrapper is
  five lines of shell and gives the caller full control over halt-on-fail
  semantics.

## Alternatives considered

- Multi-ticket runs with a hard transaction boundary. Rejected: producing
  a clean rollback for partially applied diffs across multiple tickets
  requires either a workspace branch per run (heavy) or a virtual file
  system (out of scope).
- Per-failure parallel runs. Rejected: most repair attempts touch the same
  files, so parallelism creates merge conflicts the user has to resolve.

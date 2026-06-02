# Roadmap

This document is **direction, not a changelog**. It states where AutoMaxFix is
headed and is deliberately honest about the gap between what ships today and the
larger goal. For what actually works right now, see the "Works today" table in
the [README](README.md).

## The thesis

AutoMaxFix is a **reliability layer for AI-built systems**. As more code is
written by agents (Claude, Codex, Cursor, and whatever comes next), the scarce,
valuable capability is not generating code — it is knowing when a system is
broken, proving it, proving the fix, and preventing regressions, all while
preserving safety and an audit trail.

The bet: the thing developers will want before they trust an AI-generated change
is a layer that independently verifies reliability. That layer is the product.

## The long-term loop

```
observe
  -> detect anomaly
  -> create ticket
  -> reproduce
  -> generate candidate fix
  -> validate
  -> regression test
  -> deploy or request approval
  -> monitor outcome
  -> learn
  -> (back to observe)
```

Today AutoMaxFix implements the middle of this loop and a first slice of the
front of it:

- **observe / detect** — partially shipped. Test-runner output is parsed, and
  runtime drift is detected via command checks (healthchecks, service state, log
  patterns, process liveness). Broader anomaly detection (metrics, traces,
  statistical drift) is not built.
- **reproduce -> validate -> regression test** — shipped. One ticket at a time,
  behind a human approval gate, validated against the same signal that detected
  the failure.
- **deploy** — not autonomous. AutoMaxFix applies a patch locally and writes a
  report; the CI action can open a PR. It does not deploy on its own.
- **monitor outcome** — shipped (one-shot). `automaxfix monitor` re-verifies
  passed tickets and raises a linked regression ticket when a fix stops holding.
  Scheduling is external (cron / `watch`); a managed continuous loop is still
  ahead.
- **learn** — not built. No learning across runs yet.

## What is intentionally bounded (and will stay bounded)

These are not gaps to be closed — they are design choices that keep the tool
trustworthy:

- **One ticket, then stop.** No unbounded autonomous chains.
- **Human approval by default.** `auto_approve_in_watch` is opt-in, off by default.
- **Repair stays inside the repo allowlist.** Failures whose root cause is
  outside the repository (config, infrastructure, `/etc` units) are detected,
  ticketed, and reported — never silently or fakely "fixed."
- **The fix is proven against the original signal.** A patch cannot weaken or
  edit the reproduction it must satisfy.

## Near-term direction

In rough priority order, not committed dates:

1. **Reliability ledger** — an append-only, checksummed record of every
   ticket -> patch -> validation -> outcome, surfaced as a report other tools and
   humans can trust.
2. **Broader detection** — signals beyond a single command (metrics endpoints,
   structured logs, CI history).
3. **Cross-agent integration** — make the reliability layer easy to put in front
   of any agent's output, not just a local test suite.
4. **Scheduled monitoring** — a managed continuous monitor loop on top of the
   one-shot `automaxfix monitor` shipped today.

Contributions and issues that sharpen this direction are welcome.

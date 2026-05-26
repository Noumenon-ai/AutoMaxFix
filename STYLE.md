# Style

Same rules as NOUMENON's STYLE.md, restated for AutoMaxFix.

## Output

- Two colors only: red for errors, dim for DEBUG. Nothing else.
- ASCII markers: `[OK]`, `[FAIL]`, `[WARN]`, `[SKIP]`, `->`.
- No emojis, no spinners, no animations. Plain counters.
- Errors: one line. What failed, why, what to do.

```
[OK]  ticket AMF-20260526-001 patched and verified in 47s
[FAIL] ticket AMF-20260526-002 exhausted after 3 strategies
ERROR: ticket not found: AMF-20260526-009
```

## Code

- No emojis in comments, log strings, exception messages, docstrings,
  commit messages, or README.
- Comments explain why. Code explains what. Skip the comment if the
  code already says what.
- Long descriptive names. No single-letter variables outside trivial
  loop indices.
- No clever comprehensions. Use a loop when there's branching.

## Subprocess discipline

- Use `automaxfix.utils.run_cmd` with its `timeout_seconds` argument.
- Watch mode and the run command install the SIGTERM/SIGINT handler
  from `automaxfix.reliability.install_graceful_shutdown`.
- Ticket content is sanitized before write by `automaxfix.sanitize`.
  Never persist a raw bug report.

## Commits

Conventional commits, types: `feat`, `fix`, `perf`, `refactor`,
`docs`, `test`, `build`, `ci`, `chore`, `revert`. No co-author tags
unless explicitly requested.

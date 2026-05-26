# Runbook: watch mode appears hung

## Symptoms

- `automaxfix watch` printed a "scanning" line and has produced no
  further output for longer than the configured poll interval.
- The process is still running (visible in `ps`).
- No new ticket files have appeared in `.automaxfix/tickets/`.

## Diagnose

1. Confirm the underlying test command finished. Run the configured
   command manually:

   ```
   automaxfix status
   ```

   The status command prints the active test runner and last sample.

2. Check for orphaned subprocesses:

   ```
   ps -fH -o pid,etime,cmd | rg 'pytest|automaxfix|codex'
   ```

   If a subprocess shows elapsed time greater than the configured
   `subprocess_timeout_seconds`, the timeout enforcement is the problem.

3. Inspect the last log line:

   ```
   tail -n 50 .automaxfix/logs/watch.log
   ```

   A "subprocess timed out" line indicates the underlying agent CLI did
   not respond. The watch loop should have restarted; if it did not,
   continue to recovery.

## Recover

1. Send SIGTERM to the watch process:

   ```
   pkill -TERM -f 'automaxfix watch'
   ```

   The shutdown handler in `automaxfix.reliability` flushes state and
   exits cleanly. If the process does not exit within 10s, escalate to
   SIGKILL.

2. If the test command is hung, kill it independently:

   ```
   pkill -TERM -f 'pytest'
   ```

3. Restart watch with verbose logging:

   ```
   AUTOMAXFIX_LOG_LEVEL=DEBUG automaxfix watch --interval 30
   ```

## Prevent

- Set `subprocess_timeout_seconds` in `.automaxfix/config.yaml` to a
  value below the watch interval.
- Configure JARVIS Telegram alerts on persistent failure: if the same
  ticket fails N attempts in a row, watch mode pings the owner.
- Ensure the underlying test runner produces output to stdout (some
  runners buffer output by default; force unbuffered with `-u` or set
  `PYTHONUNBUFFERED=1`).

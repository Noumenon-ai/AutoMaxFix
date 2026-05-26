"""Reliability primitives for AutoMaxFix.

Provides SIGTERM/SIGINT graceful shutdown and ticket content integrity
checksums. Subprocess timeout is already handled by automaxfix.utils.run_cmd
which passes through to subprocess.run with an enforced timeout.
"""

from __future__ import annotations

import hashlib
import signal
import sys
import threading
from typing import Callable

_shutdown_callbacks: list[Callable[[], None]] = []
_shutdown_lock = threading.Lock()
_shutdown_installed = False


def register_shutdown_callback(fn: Callable[[], None]) -> None:
    """Append a callback that runs during graceful shutdown."""
    with _shutdown_lock:
        _shutdown_callbacks.append(fn)


def install_graceful_shutdown() -> None:
    """Install SIGTERM/SIGINT handlers. Idempotent."""
    global _shutdown_installed
    if _shutdown_installed:
        return

    def _handler(signum: int, _frame: object) -> None:
        with _shutdown_lock:
            for callback in list(_shutdown_callbacks):
                try:
                    callback()
                except Exception:  # noqa: BLE001 - best effort during shutdown
                    pass
        sys.exit(128 + signum)

    try:
        signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT, _handler)
    except (ValueError, OSError):
        return
    _shutdown_installed = True


def ticket_content_checksum(payload: dict) -> str:
    """Stable sha256 over the canonical JSON encoding of a ticket payload.

    Stored in the ticket header so future loads can verify the ticket has not
    been tampered with. Excludes the checksum field itself from the hash.
    """
    import json

    filtered = {key: value for key, value in payload.items() if key != "content_sha256"}
    encoded = json.dumps(filtered, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_ticket_checksum(payload: dict) -> bool:
    """Return True if the stored sha256 matches the recomputed value.

    Tickets without a stored checksum return False; treat those as needing
    manual verification (a backfill operation upgrades them in place).
    """
    stored = payload.get("content_sha256")
    if not isinstance(stored, str) or not stored:
        return False
    return stored == ticket_content_checksum(payload)

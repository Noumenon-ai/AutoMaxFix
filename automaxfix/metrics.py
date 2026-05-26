"""Read ticket archive and produce summary statistics.

Output formats:
  - default: plain text, two-column table on stdout
  - --format json: a single JSON object on stdout

Surfaces enough to answer "what is the repair success rate of AMF over the
last 30 days" without opening any ticket by hand.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .ticket import load_ticket


def _is_ticket_path(path: Path) -> bool:
    return path.is_file() and path.suffix == ".json" and path.stem.startswith("AMF-")


def iter_tickets(tickets_dir: Path) -> Iterable[Any]:
    if not tickets_dir.is_dir():
        return
    for child in sorted(tickets_dir.iterdir()):
        if not _is_ticket_path(child):
            continue
        try:
            yield load_ticket(child)
        except Exception:  # noqa: BLE001 - best effort across archive history
            continue


def summarize(tickets_dir: Path, since_days: int | None = None) -> dict[str, Any]:
    cutoff = None
    if since_days is not None and since_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)

    total = 0
    statuses: Counter[str] = Counter()
    severities: Counter[int] = Counter()
    sources: Counter[str] = Counter()
    strategies_used: Counter[str] = Counter()
    durations: list[float] = []

    for ticket in iter_tickets(tickets_dir):
        created = getattr(ticket, "created_at", None)
        if cutoff is not None and isinstance(created, str):
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                if created_dt < cutoff:
                    continue
            except ValueError:
                pass
        total += 1
        statuses[str(getattr(ticket, "status", "unknown") or "unknown")] += 1
        severity = getattr(ticket, "severity", None)
        if isinstance(severity, int):
            severities[severity] += 1
        sources[str(getattr(ticket, "source", "unknown") or "unknown")] += 1
        memo = getattr(ticket, "strategy_memo", None)
        if memo is not None:
            attempts = getattr(memo, "attempts", []) or []
            for attempt in attempts:
                name = getattr(attempt, "strategy", None)
                if isinstance(name, str):
                    strategies_used[name] += 1
                duration = getattr(attempt, "duration_seconds", None)
                if isinstance(duration, (int, float)) and duration > 0:
                    durations.append(float(duration))

    passed = statuses.get("passed", 0) + statuses.get("complete", 0)
    failed = statuses.get("failed", 0) + statuses.get("exhausted", 0)
    success_rate = (passed / total) if total else 0.0

    return {
        "tickets_total": total,
        "tickets_passed": passed,
        "tickets_failed": failed,
        "success_rate": round(success_rate, 4),
        "by_status": dict(statuses),
        "by_severity": dict(sorted(severities.items())),
        "by_source": dict(sources),
        "strategies_used": dict(strategies_used),
        "attempt_duration_seconds": {
            "samples": len(durations),
            "mean": round(statistics.mean(durations), 2) if durations else None,
            "median": round(statistics.median(durations), 2) if durations else None,
            "max": round(max(durations), 2) if durations else None,
        },
        "window_days": since_days,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def render_text(report: dict[str, Any]) -> str:
    lines = []
    lines.append(f"tickets total      {report['tickets_total']}")
    lines.append(f"tickets passed     {report['tickets_passed']}")
    lines.append(f"tickets failed     {report['tickets_failed']}")
    lines.append(f"success rate       {report['success_rate']:.2%}")
    if report["attempt_duration_seconds"]["samples"]:
        d = report["attempt_duration_seconds"]
        lines.append(f"attempts sampled   {d['samples']}")
        lines.append(f"attempt mean s     {d['mean']}")
        lines.append(f"attempt median s   {d['median']}")
        lines.append(f"attempt max s      {d['max']}")
    if report["window_days"]:
        lines.append(f"window days        {report['window_days']}")
    if report["by_status"]:
        lines.append("by status:")
        for key, value in report["by_status"].items():
            lines.append(f"  {key:<16} {value}")
    if report["by_severity"]:
        lines.append("by severity:")
        for key, value in report["by_severity"].items():
            lines.append(f"  sev {key:<12} {value}")
    if report["strategies_used"]:
        lines.append("strategies used:")
        for key, value in report["strategies_used"].items():
            lines.append(f"  {key:<16} {value}")
    return "\n".join(lines)


def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, separators=(",", ":"), sort_keys=True)

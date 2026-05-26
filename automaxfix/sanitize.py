"""Strip credential-shaped patterns from ticket content before writing to disk.

Applied uniformly to every ticket field that may contain captured terminal
output, stack traces, environment variable dumps, or user-pasted bug reports.

Patterns are conservative: any sufficiently long, high-entropy token in a
credential-shaped position is replaced with REDACTED. False positives are
acceptable; false negatives are not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REDACTED = "[REDACTED]"

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "bearer_token",
        re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]{16,}", re.MULTILINE),
    ),
    (
        "authorization_header",
        re.compile(
            r"(?i)\b(authorization\s*[:=]\s*)\S{16,}",
            re.MULTILINE,
        ),
    ),
    (
        "common_key_envvar",
        re.compile(
            r"(?i)\b("
            r"(?:[A-Z][A-Z0-9_]*_)?"
            r"(?:API_KEY|SECRET|TOKEN|PASSWORD|PASSWD|PRIVATE_KEY|ACCESS_KEY|"
            r"CLIENT_SECRET|DB_PASSWORD|DATABASE_URL|DSN|WEBHOOK_SECRET|SESSION_SECRET)"
            r")\s*[=:]\s*\S+",
            re.MULTILINE,
        ),
    ),
    (
        "stripe_secret",
        re.compile(r"\b(sk_(?:live|test)_[A-Za-z0-9]{16,})\b"),
    ),
    (
        "github_token",
        re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,})\b"),
    ),
    (
        "openai_token",
        re.compile(r"\b(sk-[A-Za-z0-9]{20,})\b"),
    ),
    (
        "anthropic_token",
        re.compile(r"\b(sk-ant-[A-Za-z0-9_\-]{20,})\b"),
    ),
    (
        "google_api_key",
        re.compile(r"\b(AIza[0-9A-Za-z_\-]{30,})\b"),
    ),
    (
        "aws_access_key",
        re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    ),
    (
        "slack_token",
        re.compile(r"\b(xox[abprs]-[A-Za-z0-9\-]{10,})\b"),
    ),
    (
        "telegram_bot_token",
        re.compile(r"\b(\d{8,}:[A-Za-z0-9_\-]{30,})\b"),
    ),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
    ),
    (
        "private_key_block",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    (
        "dotenv_line",
        re.compile(
            r"^(?P<key>[A-Z][A-Z0-9_]{2,})=(?P<value>['\"]?[A-Za-z0-9+/_\-=.~:!@#$%^&*?]{8,}['\"]?)",
            re.MULTILINE,
        ),
    ),
)


@dataclass
class SanitizeResult:
    text: str
    redactions: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.redactions.values())


def sanitize(text: str) -> SanitizeResult:
    if not text:
        return SanitizeResult(text=text, redactions={})
    output = text
    counts: dict[str, int] = {}
    for name, pattern in _PATTERNS:
        if name == "common_key_envvar":
            output, count = pattern.subn(_replace_keyvalue, output)
        elif name == "authorization_header":
            output, count = pattern.subn(rf"\1{REDACTED}", output)
        elif name == "dotenv_line":
            output, count = pattern.subn(rf"\g<key>={REDACTED}", output)
        elif name == "private_key_block":
            output, count = pattern.subn(f"{REDACTED}_PRIVATE_KEY_BLOCK", output)
        else:
            output, count = pattern.subn(REDACTED, output)
        if count:
            counts[name] = count
    return SanitizeResult(text=output, redactions=counts)


def _replace_keyvalue(match: re.Match[str]) -> str:
    return f"{match.group(1)}={REDACTED}"


def sanitize_text(text: str) -> str:
    return sanitize(text).text


def sanitize_mapping(mapping: dict[str, object]) -> dict[str, object]:
    """Recursively sanitize string values in a JSON-shaped mapping.

    Keys are preserved as-is; only values are inspected. Lists and nested
    mappings are walked. Non-string values are passed through unchanged.
    """
    return {key: _sanitize_value(value) for key, value in mapping.items()}


def _sanitize_value(value: object) -> object:
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, dict):
        return sanitize_mapping(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value

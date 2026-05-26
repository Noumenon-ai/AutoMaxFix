# Changelog

All notable changes to this project are documented here. This file is
maintained by git-cliff against conventional commits. Do not edit manually;
new sections are appended on tag.

## [Unreleased]

### Added
- Pre-commit hooks (gitleaks, detect-secrets, ruff, large-file guard).
- CI: lint, test with 70% coverage threshold, secret scan, SBOM artifact.
- PyPI publish workflow gated on tag push and trusted publisher.
- Conventional-commits release notes via git-cliff.
- `automaxfix metrics` summarizes the local ticket archive (text or JSON).
- `automaxfix backup` archives `.automaxfix/` to a timestamped tarball.
- `automaxfix.sanitize` strips credential patterns before writing tickets.
- `automaxfix.reliability` provides SIGTERM/SIGINT graceful shutdown and
  ticket content checksums.
- `automaxfix.observability` provides JSON-line structured logging.
- ADR: 001-one-ticket-per-run.
- Runbook: watch-mode-hang.

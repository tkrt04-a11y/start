# Changelog

## 2026-03-01

### Added
- Daily/weekly/monthly pipeline scripts and task-registration scripts.
- Webhook alerting (format switch, retries, exponential backoff) and duplicate suppression.
- Metrics aggregation, operational health score, ops report generation, and static ops report index.
- Weekly artifact integrity verification and failure diagnostic report generation.
- Promoted-actions GitHub issue sync with period-key deduplication and rate-limit retries.
- JSON schema validation CLI with `schema_version` major-compatibility checks.
- Dashboard views for alerts, issue-sync monitoring, and ops/failure diagnostics.

### Changed
- CI workflow enhanced for `metrics-check` / `ops-report` schema validation and PR comment enrichment.
- Operational docs updated (runbook, schema compatibility policy, roadmap).

### Security
- Commit scope audited for secret leakage; no real credentials found.
- `.gitignore` hardened to avoid local generated artifact commits (`logs/`, `collected_data.json`, `metrics-check-result.json`, `docs/*_reports/`, `docs/improvement_backlog.md`, `survey.json`).

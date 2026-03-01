# Operations Runbook (Failure Playbooks)

This runbook documents daily/weekly/monthly pipeline commands, common failure remediation, key environment knobs, and a first-15-minute incident checklist.

## 1) Pipeline commands

### Daily pipeline

```powershell
powershell -ExecutionPolicy Bypass -File scripts/daily_pipeline.ps1
```

### Weekly pipeline

```powershell
powershell -ExecutionPolicy Bypass -File scripts/weekly_pipeline.ps1
```

### Monthly pipeline (recommended ops command set)

```powershell
python -m src.main monthly-report
python -m src.main apply-insights
python -m src.main retention
```

## 2) Common failures and remediation playbooks

### A. Connector failure (fetch failed / retry exhausted)

- Diagnose commands:
  ```powershell
  python -m src.main fetch github microsoft/vscode open 5
  python -m src.main doctor --json
  Select-String -Path logs\* -Pattern "retry exhausted|connector|command_failed" -CaseSensitive:$false
  ```
- Recovery commands:
  ```powershell
  $env:CONNECTOR_RETRIES="5"
  $env:CONNECTOR_BACKOFF_SEC="1.0"
  python -m src.main fetch rss https://hnrss.org/frontpage 20
  ```
- Stop / rollback criteria: stop the batch and roll back to previous stable defaults if the same connector fails twice in a row or remains degraded for 15+ minutes.
- Escalation trigger: escalate immediately to platform owner when multiple sources fail together or credential refresh does not restore service.

### B. Rate-limit wait exceeded (max wait exceeded)

- Diagnose commands:
  ```powershell
  Select-String -Path logs\* -Pattern "429|Retry-After|X-RateLimit-Reset|max wait" -CaseSensitive:$false
  python -m src.main fetch github microsoft/vscode open 20
  ```
- Recovery commands:
  ```powershell
  $env:CONNECTOR_MAX_WAIT_SEC="60"
  python -m src.main weekly-report --days 3
  ```
- Stop / rollback criteria: if max-wait is exceeded for two consecutive cycles after tuning, stop the affected job, restore previous max-wait value, and reduce scope.
- Escalation trigger: escalate when SLA breach risk becomes clear (for example 30+ minutes expected delay).

### C. Webhook failure (alert delivery failed)

- Diagnose commands:
  ```powershell
  Select-String -Path logs\alerts.log -Pattern "webhook_failed|ALERT_WEBHOOK" -CaseSensitive:$false
  python -m src.main doctor --json
  ```
- Recovery commands:
  ```powershell
  $env:ALERT_WEBHOOK_FORMAT="slack"
  $env:ALERT_WEBHOOK_RETRIES="5"
  python -m src.main weekly-report --days 7
  ```
- Stop / rollback criteria: pause webhook sends if destination routing is uncertain, and temporarily fall back to `logs/alerts.log`-based monitoring.
- Escalation trigger: escalate to SRE/notification owner if critical alerts are not delivered for 10+ minutes.

### D. Doctor CI failure (`doctor --json` errors)

- Diagnose commands:
  ```powershell
  python -m src.main env-init
  python -m src.main doctor --json
  ```
- Recovery commands:
  ```powershell
  python -m src.main doctor
  python -m src.main doctor --json
  ```
- Stop / rollback criteria: block merge/deploy while `doctor --json` returns errors.
- Escalation trigger: escalate to CI admin + service owner when CI fails twice after secret/config updates.

### E. Issue sync duplication (duplicate issue creation)

- Diagnose commands:
  ```powershell
  Select-String -Path docs\improvement_backlog.md -Pattern "\[Promoted\]" -CaseSensitive:$false
  python -m src.main apply-insights --dry-run
  ```
- Recovery commands:
  ```powershell
  $env:AUTO_SYNC_PROMOTED_ISSUES="0"
  python -m src.main apply-insights
  ```
- Stop / rollback criteria: disable auto-sync as soon as duplicate creation is confirmed for the same `period_key`; continue with manual review.
- Escalation trigger: escalate to product owner when duplicates exceed 3 in a week or existing issues are overwritten unexpectedly.

### F. Retention problems (archive failure / over-archiving)

- Diagnose commands:
  ```powershell
  python -m src.main retention
  Get-ChildItem archive | Select-Object -First 20
  Select-String -Path logs\* -Pattern "retention|archive|command_failed" -CaseSensitive:$false
  ```
- Recovery commands:
  ```powershell
  $env:RETENTION_DAYS="120"
  python -m src.main retention
  ```
- Stop / rollback criteria: stop retention when unexpected mass archival or storage pressure appears; restore previous `RETENTION_DAYS` and reassess.
- Escalation trigger: escalate immediately to infra owner if data-loss suspicion appears or disk usage exceeds 85%.

## 3) Decision Matrix (symptom -> action -> owner/escalation)

| Symptom | Immediate action | Owner / Escalation |
| --- | --- | --- |
| connector retry exhausted | re-run single fetch, tune `CONNECTOR_RETRIES/BACKOFF` | on-call ops, escalate to platform at 15 min |
| 429 + max wait exceeded | stop overlapping jobs, reduce range, review max wait | on-call ops, escalate when SLA risk appears |
| repeated `webhook_failed` | validate URL/format, tune retries, fallback to log monitoring | SRE, escalate after 10 min without critical delivery |
| CI `doctor --json` errors | reproduce locally via `env-init` + `doctor --json`, fix secrets | PR owner, escalate after 2 failed CI reruns |
| duplicate issues in same period | set `AUTO_SYNC_PROMOTED_ISSUES=0`, switch to manual sync | feature owner, escalate when >3/week |
| retention anomaly / storage spike | stop retention, restore previous days, inspect archive | ops + infra, immediate escalation on data-loss risk |

## 4) Environment variable matrix (major knobs)

| Variable | Purpose | Default / Example |
| --- | --- | --- |
| `OPENAI_API_KEY` | AI summary/API use | required for AI features |
| `RETENTION_DAYS` | data retention window | `90` |
| `CONNECTOR_RETRIES` | connector retry count | `3` |
| `CONNECTOR_BACKOFF_SEC` | initial retry backoff seconds | `0.5` |
| `CONNECTOR_MAX_WAIT_SEC` | max rate-limit wait seconds | `30` |
| `ALERTS_MAX_LINES` | alerts log rotation threshold | `500` |
| `ALERT_WEBHOOK_URL` | outbound alert webhook | optional |
| `ALERT_WEBHOOK_FORMAT` | webhook payload format | `generic` |
| `ALERT_WEBHOOK_RETRIES` | webhook retry count | `3` |
| `ALERT_WEBHOOK_BACKOFF_SEC` | initial webhook backoff seconds | `1.0` |
| `PROMOTED_MIN_COUNT` | promoted alert threshold | `1` |
| `AUTO_SYNC_PROMOTED_ISSUES` | enable issue auto-sync | `0` / `1` |
| `GITHUB_REPO` | issue sync target repo | `owner/repo` |
| `GITHUB_TOKEN` | issue sync token | required when sync enabled |

## 5) Incident response checklist (first 15 minutes)

1. Identify blast radius (daily/weekly/monthly impact, first failure timestamp, recent changes).
2. Check `logs/alerts.log` and CI output; classify failure type.
3. Reproduce with a single command to separate transient vs persistent failures.
4. Validate credentials and env vars (`OPENAI_API_KEY`, `GITHUB_TOKEN`, webhook URL).
5. Apply mitigations (retry/backoff/wait/job staggering) and rerun.
6. If not recovered within ~15 minutes, publish status update (impact, mitigation, next action, next ETA).

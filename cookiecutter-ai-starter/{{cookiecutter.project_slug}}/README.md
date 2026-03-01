# {{ cookiecutter.project_name }}

{{ cookiecutter.description }}

## Setup

1. Create a Python virtual environment:
   ```sh
   python -m venv venv
   .\\venv\\Scripts\\activate
   ```
2. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```

### Safer API key setup (recommended)

Avoid typing the key directly in command history:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/set_openai_key.ps1
```

## Usage

Run the main script:
```sh
python -m src.main
```

### Information collection

A simple helper is included to gather notes or ideas you want the
starter kit to remember. It can be invoked from the command line:

```sh
python -m src.main collect
```

Data is written into `collected_data.json` in the current directory.

python -m src.main analyze
```

AI summary:

```sh
python -m src.main analyze --ai --model gpt-4o-mini
```

### Automatic connectors

```sh
python -m src.main fetch github microsoft/vscode open 20
python -m src.main fetch rss https://hnrss.org/frontpage 20
python -m src.main fetch survey-json survey.json content
```

### Apply insights

```sh
python -m src.main apply-insights
python -m src.main apply-insights --ai
python -m src.main apply-insights --dry-run
```

With `--dry-run`, no files are written and a diff summary (new_file/unchanged/changed with +N/-M line counts) is shown for `docs/improvement_backlog.md` and `.github/instructions/common.instructions.md`.

Apply data retention policy (default: 90 days) and archive old data into `archive/`:

```sh
python -m src.main retention
```

Retention covers `collected_data.json`, `logs/activity_history.jsonl`, `logs/alerts.log`, and
`logs/*-metrics-*.json`; expired metrics files are moved into `archive/metrics/`.

Configuration check:
```sh
python -m src.main doctor
python -m src.main doctor --json
python -m src.main env-init
```

`doctor --json` can be used in CI to fail fast when configuration errors are detected.

If `docs/weekly_reports/latest_weekly_report.md` exists, `Action:` lines from Spotlight
are extracted and copied into the `## Spotlight Actions` checklist in
`docs/improvement_backlog.md`.
Priority labels are auto-assigned as `[High]` / `[Med]` / `[Low]` based on delta magnitude.
The checklist is auto-sorted in `High -> Med -> Low` order.
When generating weekly reports (`weekly-report --days N`), `High` Spotlight actions are
auto-promoted into `## Action Items` with a `[Promoted]` label.
During `apply-insights`, those `[Promoted]` lines are synced into
`## Promoted This Week` in `docs/improvement_backlog.md`.

`apply-insights` output also prints synced `Spotlight` and `Promoted` counts,
which is useful for daily/weekly pipeline log monitoring.
If promoted actions are below threshold (`PROMOTED_MIN_COUNT`, default 1),
it prints `Warning: promoted actions below threshold (...)`.
Daily/weekly pipelines append these warnings to `logs/alerts.log`.
When `ALERTS_MAX_LINES` is exceeded, alerts are rotated into `alerts-YYYYMMDD-HHMMSS.log`.
If `ALERT_WEBHOOK_URL` is set, alert messages are sent to the webhook.
Webhook notifications for identical alert signatures (timestamp-stripped alert body) are suppressed within `ALERT_DEDUP_COOLDOWN_SEC` (default: 600 seconds).
Dedup state is persisted in `logs/alert_dedup_state.json`, and notifications are sent again after cooldown expires.
Dedup state entries older than `ALERT_DEDUP_TTL_SEC` (default: 604800 seconds = 7 days) are automatically pruned to prevent unbounded growth.
Webhook payload format is selectable with `ALERT_WEBHOOK_FORMAT` as `generic` / `slack` / `teams` (default: `generic`).
Pipeline run logs (`logs/*-run-*.log` / `logs/alerts.log`) and alert summaries (`logs/alerts-summary-*.md`) are written in UTF-8 (without BOM).

Inspect/reset dedup state:

```sh
python -m src.main alert-dedup-status
python -m src.main alert-dedup-status --json
python -m src.main alert-dedup-reset
python -m src.main alert-dedup-reset --backup
python -m src.main alert-dedup-prune
python -m src.main alert-dedup-prune --json
```

`alert-dedup-status` shows entry count, oldest/newest timestamps, and top signatures from `logs/alert_dedup_state.json`.
`alert-dedup-reset` safely clears dedup state, and creates a backup file when `--backup` is provided.
`alert-dedup-prune` force-prunes expired dedup entries immediately and prints removed count.

### Pipeline metrics artifacts

After each daily/weekly/monthly pipeline run, machine-readable metrics JSON is emitted under `logs/` (UTF-8 without BOM):

- `logs/daily-metrics-YYYYMMDD-HHMMSS.json`
- `logs/weekly-metrics-YYYYMMDD-HHMMSS.json`
- `logs/monthly-metrics-YYYYMMDD-HHMMSS.json`

Each file includes `pipeline`, `started_at`, `finished_at`, `duration_sec`, `command_failures`, `alert_count`, `promoted_threshold`, `promoted_detected`, `monthly_report_target`, `webhook_format`, and `success`.

Threshold check (exit code `1` when violations exist):

```sh
python -m src.main metrics-check
python -m src.main metrics-check --days 30
python -m src.main metrics-check --days 14 --json
```

In GitHub Actions CI, the `build` job now runs this gate after tests:

```sh
python -m src.main metrics-check --days 30 --json
```

`metrics-check --json` output is fixed by `docs/schemas/metrics_check.schema.json`.
The payload includes `schema_version` (current: `1.1.0`).
Local validation example:

```sh
python scripts/ci/validate_json_schema.py --input metrics-check-result.json --schema docs/schemas/metrics_check.schema.json --compatibility major
```

For JSON Schema versioning/compatibility/breaking-change/CI policy, see
`docs/schema_compatibility_policy.md`.

If any threshold violations are detected, it exits with code `1` and fails the job.
On `pull_request` events, CI also posts the `metrics-check` result to a PR comment.
The workflow updates a single marker comment (`<!-- ai-starter:metrics-check -->`) instead of adding duplicates on every run.
When a previous snapshot (`logs/metrics-check-ci-prev.json`) is available, the same comment also includes deltas for
`violation_count`, `health_score` (when present), and per-pipeline violation counts (`daily` / `weekly` / `monthly`).
If the previous snapshot is missing or unreadable, the comparison section is skipped gracefully.
The PR comment includes the active `threshold_profile` and a concise table of effective resolved thresholds
(`daily/weekly/monthly` for `max_duration_sec` and `max_failure_rate`, including env overrides).
At the end of the same comment, CI also appends `pipeline` / `suggested_retry_command` / `runbook_reference`
from `failed_command_retry_guides` in `logs/ops-report-ci.json` (with graceful fallback when unavailable).
When there are no violations, the same comment is updated to a `✅ pass` status.
For this behavior, workflow permissions are minimized to `contents: read` and `issues: write`.
Configure these threshold environment variables in repository/environment settings for your policy:

- `METRIC_THRESHOLD_PROFILE` (`dev` / `stg` / `prod`, default: `prod`)
- `METRIC_MAX_DURATION_DAILY_SEC`
- `METRIC_MAX_DURATION_WEEKLY_SEC`
- `METRIC_MAX_DURATION_MONTHLY_SEC`
- `METRIC_MAX_FAILURE_RATE_DAILY`
- `METRIC_MAX_FAILURE_RATE_WEEKLY`
- `METRIC_MAX_FAILURE_RATE_MONTHLY`

`METRIC_THRESHOLD_PROFILE` selects the baseline threshold set by environment.
`dev` is looser, `stg` is medium, and `prod` is strict.
Unknown profile values safely fall back to `prod`.
Explicit `METRIC_MAX_DURATION_*` / `METRIC_MAX_FAILURE_RATE_*` values override profile defaults.

`metrics-check` evaluates `logs/*-metrics-*.json` in the selected window and reports per-pipeline violations for `max_duration_sec` and `failure_rate`.
Exit code is `1` when one or more violations are found, otherwise `0`.

`metrics-summary` uses the same source metrics and also emits unified health fields:
`health_score` and `health_breakdown` (`factors` / `penalties` / `formula`) in both text and JSON output.

In the dashboard Metrics tab, the same aggregated inputs are also shown as a single `Health score` (0-100).
It is a lightweight operational signal computed from:

- average pipeline success rate (penalty: `(1 - avg_success_rate) * 60`)
- threshold violation count (penalty: `min(25, violations * 5)`)
- command failure count (penalty: `min(10, command_failures * 2)`)
- alert volume as an optional light penalty (penalty: `min(5, alert_count * 0.2)`)

Final score is `100 - total_penalty`, then clamped to `0..100`.

When `logs/weekly-ops-failure-diagnostic.md` exists, the dashboard Metrics tab also shows
the latest weekly failure diagnostic summary (generated time, failure reasons, and required-file checks).
If the file does not exist, an informational guide message is shown instead.

### Weekly operational health report

Generate an operational health report (default window: last 7 days):

```sh
python -m src.main ops-report
python -m src.main ops-report --days 14
python -m src.main ops-report --days 7 --json
python -m src.main ops-report-index --limit 8
```

Generated files:
- `docs/ops_reports/ops-report-YYYY-MM-DD.md`
- `docs/ops_reports/latest_ops_report.md`
- `docs/ops_reports/ops-report-YYYY-MM-DD.html`
- `docs/ops_reports/latest_ops_report.html`
- `docs/ops_reports/index.html`

Running `ops-report` also refreshes `docs/ops_reports/index.html`, which links the latest report and recent dated reports in both Markdown and HTML.
The weekly pipeline (`scripts/weekly_pipeline.ps1`) runs `ops-report-index` immediately after `ops-report` to keep the index current.

The report includes pipeline success rates, threshold violation counts (same logic as `metrics-check`), top alert types from `logs/alerts.log`, and recent command failure counts.
It also includes a failed-command retry guide extracted from `logs/*-run-*.log` with `pipeline`, `failed_command`, `suggested_retry_command`, `runbook_reference`, and `runbook_reference_anchor`.
It also includes the same unified health fields as `metrics-summary`: `health_score` and `health_breakdown` (consistent naming in md/html/json).
In addition, daily alert summaries from `logs/alerts-summary-YYYYMMDD.md` are attached under `Daily Alert Summaries` (excluding `-weekly` summary files).
In addition, artifact verification from `logs/weekly-artifact-verify.json` is embedded as `artifact_integrity` (JSON) / `Artifact Integrity` (Markdown/HTML) with `OK/MISSING` rows and missing count.

With `--json`, the same Markdown/HTML report files are still generated, and a machine-readable JSON payload is emitted to stdout.

In GitHub Actions CI, the build job runs `python -m src.main ops-report --days 7 --json > logs/ops-report-ci.json` and uploads an `ops-report-ci` artifact containing `logs/ops-report-ci.json` (plus `docs/ops_reports/latest_ops_report.md/html`).

`ops-report --json` output is fixed by `docs/schemas/ops_report.schema.json`.
The payload includes `schema_version` (current: `1.1.0`).
Local validation example:

```sh
python scripts/ci/validate_json_schema.py --input logs/ops-report-ci.json --schema docs/schemas/ops_report.schema.json --compatibility major
```

For weekly publishing, `.github/workflows/weekly-ops-report.yml` is included.
It runs `ops-report` and `ops-report-index` on schedule (or manual dispatch) and uploads a `weekly-ops-report` artifact.
Before uploading, it runs `python scripts/ci/verify_weekly_ops_artifacts.py --json-output logs/weekly-artifact-verify.json` to verify `docs/ops_reports/latest_ops_report.md`, `latest_ops_report.html`, `index.html`, and `logs/ops-report-ci.json`; missing files fail the job.
When the job fails, it also runs `python scripts/ci/generate_weekly_failure_diagnostic.py` and uploads a `weekly-ops-failure-diagnostic` artifact that includes executed commands, failure reasons, required-file checks, and a latest log excerpt.
Safe default is artifact-only; GitHub Pages deployment is enabled only when `.github/pages-deploy.enabled` exists in the repository.

With `AUTO_SYNC_PROMOTED_ISSUES=1` (or `--sync-issues`), promoted actions are auto-created
as GitHub issues using `GITHUB_REPO` and `GITHUB_TOKEN`.
To avoid duplicate issue creation in the same period, `period_key` is stored in issue body metadata,
and duplicate checks use title match or `action_hash + period_key` match.
`period_key` uses the weekly label for weekly promoted actions (for example `2026-W09`) and
the month label for monthly promoted actions (for example `2026-02`).
Issue bodies are generated from a shared template with `Source Period` / `Action` / `Context` / `Metadata` sections.
Set `GITHUB_ISSUE_PERIOD_LABELS=1` to auto-add period labels (`ai-starter-weekly` / `ai-starter-monthly`) in addition to existing labels.
Assignees are resolved with priority: explicit `GITHUB_ISSUE_ASSIGNEES` > label-based `GITHUB_ISSUE_ASSIGNEE_RULES` > `default` rule.
Set `GITHUB_ISSUE_ASSIGNEE_RULES` as `label:assignee1,assignee2;default:teamlead`,
for example: `ai-starter-weekly:alice;ai-starter-monthly:bob;default:teamlead`.
If `GITHUB_ISSUE_ASSIGNEE_RULES` contains invalid syntax (for example missing `:`, empty label, or empty assignee list),
issue sync is safely skipped and an error message is printed.
Issue sync GitHub API calls detect 429 / secondary rate limits, wait, and retry.
Wait seconds prefer `Retry-After` / `X-RateLimit-Reset`; if absent, exponential backoff is used, and failures include status/message/attempt details.
You can override retry settings with `ISSUE_SYNC_RETRIES` (default: 3) and `ISSUE_SYNC_BACKOFF_SEC` (default: 1.0).
Invalid values safely fall back to defaults and are distinguishable in warning logs.
Monthly promoted actions are extracted from `[Promoted]` lines under
`## Promotable Actions` in `docs/monthly_reports/latest_monthly_report.md`.

Key `.env` settings:
- `OPENAI_API_KEY`: OpenAI API key
- `RETENTION_DAYS`: retention days for collected/log data (default: 90)
- `PROMOTED_MIN_COUNT`: promoted threshold (default: 1)
- `ALERTS_MAX_LINES`: `logs/alerts.log` rotation line count (default: 500)
- `ALERT_WEBHOOK_URL`: optional alert webhook URL
- `ALERT_WEBHOOK_FORMAT`: webhook payload format (`generic` / `slack` / `teams`, default: `generic`)
- `ALERT_WEBHOOK_RETRIES`: webhook retry count for alerts (default: 3)
- `ALERT_WEBHOOK_BACKOFF_SEC`: initial webhook backoff seconds (exponential, default: 1.0)
- `ALERT_DEDUP_COOLDOWN_SEC`: webhook dedup cooldown seconds for identical alerts (default: 600, set `0` to disable)
- `ALERT_DEDUP_TTL_SEC`: retention seconds for dedup state entries (default: 604800 = 7 days, set `0` to disable TTL pruning)
- `CONNECTOR_RETRIES`: connector retry count (default: 3)
- `CONNECTOR_BACKOFF_SEC`: initial retry backoff seconds (default: 0.5)
- `CONNECTOR_MAX_WAIT_SEC`: max wait seconds for rate-limit reset (default: 30)
- `METRIC_THRESHOLD_PROFILE`: threshold profile (`dev` / `stg` / `prod`, default: `prod`, unknown values fall back to `prod`)
- `METRIC_MAX_DURATION_DAILY_SEC`: daily `max_duration_sec` threshold in seconds (default: 900)
- `METRIC_MAX_DURATION_WEEKLY_SEC`: weekly `max_duration_sec` threshold in seconds (default: 1800)
- `METRIC_MAX_DURATION_MONTHLY_SEC`: monthly `max_duration_sec` threshold in seconds (default: 3600)
- `METRIC_MAX_FAILURE_RATE_DAILY`: daily `failure_rate` threshold (0-1, default: 0.10)
- `METRIC_MAX_FAILURE_RATE_WEEKLY`: weekly `failure_rate` threshold (0-1, default: 0.20)
- `METRIC_MAX_FAILURE_RATE_MONTHLY`: monthly `failure_rate` threshold (0-1, default: 0.25)
- `AUTO_SYNC_PROMOTED_ISSUES`: set `1` to enable issue auto-sync
- `GITHUB_REPO`: `owner/repo`
- `GITHUB_TOKEN`: GitHub API token
- `GITHUB_ISSUE_LABELS`: comma-separated issue labels
- `GITHUB_ISSUE_ASSIGNEES`: comma-separated issue assignees
- `ISSUE_SYNC_RETRIES`: issue sync retry count (default: 3)
- `ISSUE_SYNC_BACKOFF_SEC`: initial issue sync backoff seconds for exponential retry (default: 1.0)
- `GITHUB_ISSUE_ASSIGNEE_RULES`: label-based assignee routing (`;`-separated `label:assignee1,assignee2`, with `default` fallback; invalid syntax skips sync)
- `GITHUB_ISSUE_PERIOD_LABELS`: set `1` to auto-attach weekly/monthly period labels (default: `0`)

### Weekly report

```sh
python -m src.main weekly-report
python -m src.main weekly-report --ai
python -m src.main weekly-report --days 14
python -m src.main weekly-report --all
```

Default range is last 7 days (`--days N` to change, `--all` for all data).
When using a finite range (`--days N`), the report also shows deltas vs the previous N-day window.

Generated files:
- `docs/weekly_reports/weekly-report-YYYY-Www.md`
- `docs/weekly_reports/latest_weekly_report.md`
- `docs/weekly_reports/weekly-report-YYYY-Www.html`
- `docs/weekly_reports/latest_weekly_report.html`

### Monthly report

```sh
python -m src.main monthly-report
python -m src.main monthly-report --month 2026-02
python -m src.main monthly-report --ai
```

If `--month` is omitted, the current month (`YYYY-MM`) is used.
Monthly reports include only entries with `collected_at` timestamps and exclude missing timestamps for deterministic output.
When comparable data is available, monthly reports also include period-over-period deltas vs the previous month and a Spotlight (Top 3 Changes) with action recommendations.

Generated files:
- `docs/monthly_reports/monthly-report-YYYY-MM.md`
- `docs/monthly_reports/latest_monthly_report.md`
- `docs/monthly_reports/monthly-report-YYYY-MM.html`
- `docs/monthly_reports/latest_monthly_report.html`

In `scripts/daily_pipeline.ps1` and `scripts/weekly_pipeline.ps1`, on the first day of each month, the previous month (`YYYY-MM`) is auto-generated via `monthly-report --ai`.
`scripts/monthly_pipeline.ps1` always generates the previous month (`YYYY-MM`) via `monthly-report --ai`.

### Web UI

```sh
streamlit run src/dashboard.py
```

`History` tab provides timestamped operation history in `logs/activity_history.jsonl`.
`Alerts` tab shows alert count and recent lines from `logs/alerts.log`.
The same tab also shows period-based pipeline breakdown (`daily/weekly/unknown`) and type breakdown (`threshold/webhook_failed/command_failed/other`).
`Metrics` tab shows pipeline run counts, success rates, duration (avg/max), totals (`command_failures`/`alert_count`), and latest run info by pipeline.
The same tab includes an `Issue Sync` monitoring card for success/failure/retry counts (prefers `logs/activity_history.jsonl` / `logs/activity_log.jsonl`; missing retry count is shown as `N/A`; falls back to `logs/*-run-*.log`).
The same tab also lets you browse the latest ops report summary from `docs/ops_reports/latest_ops_report.md` and preview history from `docs/ops_reports/ops-report-*.md`.
Inside `Ops Report (latest)` on the same tab, `Daily Alert Summaries` are shown as a table; if the section is missing in ops-report, daily files in `logs/alerts-summary-YYYYMMDD.md` are used as fallback.

HTTP connectors use retries (`CONNECTOR_RETRIES`, `CONNECTOR_BACKOFF_SEC`).
On 429 or GitHub rate-limit headers, connectors wait using `X-RateLimit-Reset` / `Retry-After` up to `CONNECTOR_MAX_WAIT_SEC` (default: 30s) and then retry.
Conditional fetch with ETag / If-Modified-Since reduces duplicate HTTP traffic.

### Operations runbook

See `docs/runbook.md` for failure playbooks, major environment knobs, and the first-15-minute incident checklist.

### Scheduled runs (Windows Task Scheduler)

Use the unified registration script to register daily/weekly/monthly tasks in one command.

Register all pipelines with defaults (daily/weekly/monthly):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_pipeline_tasks.ps1
```

Register only weekly and monthly:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_pipeline_tasks.ps1 -Pipelines weekly,monthly
```

Customize day/time values in one command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_pipeline_tasks.ps1 -DailyTime "21:30" -WeeklyDay MON -WeeklyTime "08:30" -MonthlyDay 5 -MonthlyTime "08:45"
```

Preview commands without executing task registration (DryRun):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_pipeline_tasks.ps1 -Pipelines weekly,monthly -DryRun
```

Run input validation only (ValidateOnly):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_pipeline_tasks.ps1 -Pipelines daily,weekly -DailyTime "21:30" -WeeklyDay MON -WeeklyTime "08:30" -ValidateOnly
```

Defaults:
- Daily: `AIStarterDailyPipeline` / `09:00`
- Weekly: `AIStarterWeeklyPipeline` / `SUN` / `09:30`
- Monthly: `AIStarterMonthlyPipeline` / day `1` / `10:00`

For backward compatibility, the legacy scripts are still available:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_daily_task.ps1 -Time "21:30" -DryRun
powershell -ExecutionPolicy Bypass -File scripts/register_weekly_task.ps1 -Day MON -Time "08:30" -ValidateOnly
powershell -ExecutionPolicy Bypass -File scripts/register_monthly_task.ps1 -Day 5 -Time "08:45"
```

## Testing

```sh
pytest
```

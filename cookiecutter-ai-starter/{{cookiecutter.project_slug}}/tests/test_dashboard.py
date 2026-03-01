from pathlib import Path

from src.dashboard import (
    _collect_issue_sync_stats,
    _load_daily_alert_summaries_from_logs,
    _parse_ops_report_markdown,
    _parse_weekly_failure_diagnostic_markdown,
)


def test_parse_ops_report_markdown_parses_daily_alert_summaries() -> None:
    text = "\n".join(
        [
            "# Ops Report (2026-03-01)",
            "",
            "## Window",
            "- Days: 7",
            "- Total runs: 10",
            "",
            "## Daily Alert Summaries",
            "- 2026-03-01: command_failures=2, alert_count=5",
            "- 2026-02-28: command_failures=0, alert_count=1",
            "",
            "## Artifact Integrity",
            "- Summary: ok=3, missing=1, total=4",
            "- [OK] docs/ops_reports/latest_ops_report.md",
            "- [MISSING] docs/ops_reports/index.html",
            "",
            "## Command Failures",
            "- Recent command failures: 2",
        ]
    )

    parsed = _parse_ops_report_markdown(text)

    rows = parsed.get("daily_alert_summary_rows")
    assert isinstance(rows, list)
    assert rows == [
        {"date": "2026-03-01", "command_failures": 2, "alert_count": 5},
        {"date": "2026-02-28", "command_failures": 0, "alert_count": 1},
    ]
    assert parsed.get("artifact_integrity_ok") == 3
    assert parsed.get("artifact_integrity_missing") == 1
    assert parsed.get("artifact_integrity_total") == 4
    assert parsed.get("artifact_integrity_rows") == [
        {"status": "OK", "path": "docs/ops_reports/latest_ops_report.md"},
        {"status": "MISSING", "path": "docs/ops_reports/index.html"},
    ]


def test_load_daily_alert_summaries_from_logs_uses_daily_files_only(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    (logs_dir / "alerts-summary-20260301.md").write_text(
        "\n".join(
            [
                "# Alert Summary (Daily)",
                "- Command failures: 1",
                "- Alert count: 3",
            ]
        ),
        encoding="utf-8",
    )
    (logs_dir / "alerts-summary-20260228.md").write_text(
        "\n".join(
            [
                "# Alert Summary (Daily)",
                "- Command failures: 0",
                "- Alert count: 2",
            ]
        ),
        encoding="utf-8",
    )
    (logs_dir / "alerts-summary-20260301-weekly.md").write_text("# weekly\n", encoding="utf-8")

    rows = _load_daily_alert_summaries_from_logs(logs_dir, limit=7)

    assert rows == [
        {"date": "2026-03-01", "command_failures": 1, "alert_count": 3},
        {"date": "2026-02-28", "command_failures": 0, "alert_count": 2},
    ]


def test_collect_issue_sync_stats_prefers_activity_logs(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "activity_history.jsonl").write_text(
        "\n".join(
            [
                '{"event":"apply_insights","details":{"issue_sync_created":2,"issue_sync_failed":1,"issue_sync_retries":3}}',
                '{"event":"apply_insights","details":{"issue_sync_created":1,"issue_sync_failed":0}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (logs_dir / "weekly-run-20260301-093001.log").write_text(
        "Issue sync: created=99 skipped_existing=0\nIssue sync skipped: set GITHUB_REPO and GITHUB_TOKEN.\n",
        encoding="utf-8",
    )

    stats = _collect_issue_sync_stats(logs_dir)

    assert stats == {
        "success": 3,
        "failure": 1,
        "retries": 3,
        "source": "activity_history.jsonl",
    }


def test_collect_issue_sync_stats_falls_back_to_run_logs(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "daily-run-20260301-090003.log").write_text(
        "\n".join(
            [
                "Issue sync: created=2 skipped_existing=1",
                "Issue sync skipped: set GITHUB_REPO and GITHUB_TOKEN.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    stats = _collect_issue_sync_stats(logs_dir)

    assert stats == {
        "success": 2,
        "failure": 1,
        "retries": 0,
        "source": "*-run-*.log",
    }


def test_parse_weekly_failure_diagnostic_markdown_parses_latest_summary() -> None:
    text = "\n".join(
        [
            "# Weekly Workflow Failure Diagnostic",
            "",
            "- Generated at (UTC): 2026-03-01T09:30:18+00:00",
            "",
            "## Failure Reasons",
            "- Step 'verify_weekly_artifacts' ended with outcome: failure",
            "- Required artifact files are missing: docs/ops_reports/index.html",
            "",
            "## Required File Verification",
            "- [OK] docs/ops_reports/latest_ops_report.md",
            "- [MISSING] docs/ops_reports/index.html",
        ]
    )

    parsed = _parse_weekly_failure_diagnostic_markdown(text)

    assert parsed.get("generated_at") == "2026-03-01T09:30:18+00:00"
    assert parsed.get("failure_reasons") == [
        "Step 'verify_weekly_artifacts' ended with outcome: failure",
        "Required artifact files are missing: docs/ops_reports/index.html",
    ]
    assert parsed.get("required_file_checks") == [
        {"status": "OK", "path": "docs/ops_reports/latest_ops_report.md"},
        {"status": "MISSING", "path": "docs/ops_reports/index.html"},
    ]


def test_parse_weekly_failure_diagnostic_markdown_returns_empty_for_blank() -> None:
    assert _parse_weekly_failure_diagnostic_markdown("\n") == {}

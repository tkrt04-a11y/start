from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path

from src.ops_report import build_ops_report_data, write_ops_report
from src.ops_report_index import write_ops_reports_index
from src.schema_validation import load_json_schema, validate_json_payload
from src.schema_versions import SCHEMA_VERSION


def _write_metric(logs_dir, name: str, payload: dict) -> None:
    (logs_dir / name).write_text(json.dumps(payload), encoding="utf-8")


def _load_ops_report_schema() -> dict:
    return load_json_schema(Path("docs/schemas/ops_report.schema.json"))


def test_build_ops_report_data_aggregates_metrics_alerts_and_failures(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    now = datetime(2026, 3, 1, 10, 0, 0)
    recent = (now - timedelta(days=1)).isoformat()
    old = (now - timedelta(days=20)).isoformat()

    _write_metric(
        logs_dir,
        "daily-metrics-20260301-010101.json",
        {
            "pipeline": "daily",
            "finished_at": recent,
            "duration_sec": 12,
            "command_failures": 2,
            "alert_count": 1,
            "success": False,
        },
    )
    _write_metric(
        logs_dir,
        "weekly-metrics-20260301-020202.json",
        {
            "pipeline": "weekly",
            "finished_at": recent,
            "duration_sec": 20,
            "command_failures": 1,
            "alert_count": 2,
            "success": True,
        },
    )
    _write_metric(
        logs_dir,
        "monthly-metrics-20260201-030303.json",
        {
            "pipeline": "monthly",
            "finished_at": old,
            "duration_sec": 30,
            "command_failures": 5,
            "alert_count": 5,
            "success": True,
        },
    )

    (logs_dir / "alerts.log").write_text(
        "\n".join(
            [
                f"[{recent}] WARNING weekly pipeline: command failed: python -m src.main analyze --ai",
                f"[{recent}] WARNING weekly pipeline: metrics-check reported threshold violations",
                f"[{recent}] ERROR weekly pipeline: alert webhook final failure after 3 attempts",
                f"[{old}] WARNING weekly pipeline: command failed: python -m src.main retention",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (logs_dir / "alerts-summary-20260301.md").write_text(
        "\n".join(
            [
                "# Alert Summary (Daily)",
                "",
                "Generated: 2026-03-01T08:00:00",
                "- Command failures: 1",
                "- Alert count: 2",
                "",
                "## Alerts",
                "- [2026-03-01T08:00:00] WARNING daily pipeline: promoted actions below threshold (0 < 1)",
                "- [2026-03-01T08:05:00] WARNING daily pipeline: metrics-check reported threshold violations",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (logs_dir / "alerts-summary-20260301-weekly.md").write_text("# weekly\n", encoding="utf-8")
    (logs_dir / "daily-run-20260301-090000.log").write_text(
        "\n".join(
            [
                "=== Daily pipeline started: 2026-03-01T09:00:00 ===",
                ">>> python -m src.main analyze --ai",
                "[2026-03-01T09:10:00] ERROR daily pipeline: command failed: python -m src.main analyze --ai",
                ">>> python -m src.main retention",
                "[2026-03-01T09:12:00] ERROR daily pipeline: command failed: python -m src.main retention",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (logs_dir / "weekly-run-20260301-093000.log").write_text(
        "\n".join(
            [
                "=== Weekly pipeline started: 2026-03-01T09:30:00 ===",
                ">>> python -m src.main ops-report --days 7",
                "[2026-03-01T09:45:00] ERROR weekly pipeline: command failed: python -m src.main ops-report --days 7",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (logs_dir / "monthly-run-20260201-010101.log").write_text(
        "[2026-02-01T01:10:00] ERROR monthly pipeline: command failed: python -m src.main retention\n",
        encoding="utf-8",
    )
    (logs_dir / "weekly-artifact-verify.json").write_text(
        json.dumps(
            {
                "checks": [
                    {"path": "docs/ops_reports/latest_ops_report.md", "status": "OK"},
                    {"path": "docs/ops_reports/index.html", "status": "MISSING"},
                ],
                "summary": {"total": 2, "ok": 1, "missing": 1},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_ops_report_data(
        days=7,
        logs_dir=logs_dir,
        now=now,
        env={
            "METRIC_MAX_DURATION_DAILY_SEC": "10",
            "METRIC_MAX_FAILURE_RATE_DAILY": "0.2",
        },
    )

    assert report["days"] == 7
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["recent_command_failures"] == 3
    assert "health_score" in report
    assert "health_breakdown" in report
    assert isinstance(report["health_breakdown"], dict)
    assert report["pipeline_success_rates"]["daily"]["runs"] == 1
    assert report["pipeline_success_rates"]["daily"]["success_rate"] == 0.0
    assert report["pipeline_success_rates"]["weekly"]["success_rate"] == 1.0
    assert report["threshold_violations_count"] >= 2

    top_types = {item["type"]: item["count"] for item in report["top_alert_types"]}
    assert top_types.get("command_failed", 0) == 1
    assert top_types.get("threshold", 0) == 1
    assert top_types.get("webhook_failed", 0) == 1
    assert len(report["daily_alert_summaries"]) == 1
    assert report["daily_alert_summaries"][0]["date"] == "2026-03-01"
    assert report["daily_alert_summaries"][0]["command_failures"] == 1
    assert report["daily_alert_summaries"][0]["alert_count"] == 2
    assert len(report["daily_alert_summaries"][0]["alerts"]) == 2
    artifact_integrity = report["artifact_integrity"]
    assert artifact_integrity["ok_count"] == 1
    assert artifact_integrity["missing_count"] == 1
    assert artifact_integrity["total_count"] == 2
    assert artifact_integrity["files"] == [
        {"path": "docs/ops_reports/latest_ops_report.md", "status": "OK"},
        {"path": "docs/ops_reports/index.html", "status": "MISSING"},
    ]
    guides = report["failed_command_retry_guides"]
    assert len(guides) == 3
    assert guides[0]["pipeline"] == "weekly"
    assert guides[0]["failed_command"] == "python -m src.main ops-report --days 7"
    assert guides[0]["suggested_retry_command"] == "python -m src.main ops-report --days 7"
    assert guides[0]["runbook_reference"] == "docs/runbook.md#週次パイプライン"
    assert guides[0]["runbook_reference_anchor"] == "#週次パイプライン"
    validate_json_payload(report, _load_ops_report_schema(), schema_name="ops_report.schema.json")


def test_write_ops_report_creates_markdown_and_html_outputs(tmp_path):
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": "2026-03-01T12:34:56",
        "days": 7,
        "window_start": "2026-02-23T12:34:56",
        "total_runs": 2,
        "health_score": 88,
        "health_breakdown": {
            "factors": {
                "average_pipeline_success_rate": 0.9,
                "violation_count": 1,
                "command_failures": 1,
                "alert_count": 2,
            },
            "penalties": {
                "success_rate": 6.0,
                "violations": 5.0,
                "command_failures": 2.0,
                "alerts": 0.4,
            },
            "formula": "score = ...",
        },
        "pipeline_success_rates": {
            "daily": {"runs": 1, "success_rate": 1.0},
            "weekly": {"runs": 1, "success_rate": 0.0},
        },
        "threshold_violations_count": 1,
        "threshold_violations_by_pipeline": {"weekly": 1},
        "top_alert_types": [{"type": "threshold", "count": 2}],
        "daily_alert_summaries": [
            {
                "date": "2026-03-01",
                "command_failures": 1,
                "alert_count": 2,
                "alerts": [
                    "[2026-03-01T08:00:00] WARNING daily pipeline: promoted actions below threshold (0 < 1)",
                ],
            }
        ],
        "artifact_integrity": {
            "source": "logs/weekly-artifact-verify.json",
            "ok_count": 3,
            "missing_count": 1,
            "total_count": 4,
            "files": [
                {"path": "docs/ops_reports/latest_ops_report.md", "status": "OK"},
                {"path": "docs/ops_reports/latest_ops_report.html", "status": "OK"},
                {"path": "docs/ops_reports/index.html", "status": "MISSING"},
            ],
        },
        "recent_command_failures": 1,
        "failed_command_retry_guides": [
            {
                "pipeline": "daily",
                "failed_command": "python -m src.main retention",
                "suggested_retry_command": "python -m src.main retention",
                "runbook_reference": "docs/runbook.md#日次パイプライン",
                "runbook_reference_anchor": "#日次パイプライン",
            }
        ],
    }

    report_path = write_ops_report(report, output_dir=tmp_path / "docs" / "ops_reports")

    assert report_path.name == "ops-report-2026-03-01.md"
    assert report_path.exists()
    assert (tmp_path / "docs" / "ops_reports" / "latest_ops_report.md").exists()
    assert (tmp_path / "docs" / "ops_reports" / "ops-report-2026-03-01.html").exists()
    assert (tmp_path / "docs" / "ops_reports" / "latest_ops_report.html").exists()
    assert (tmp_path / "docs" / "ops_reports" / "index.html").exists()

    text = report_path.read_text(encoding="utf-8")
    assert "health_score: 88" in text
    assert "health_breakdown" in text
    assert "## Daily Alert Summaries" in text
    assert "2026-03-01: command_failures=1, alert_count=2" in text
    assert "## Artifact Integrity" in text
    assert "Summary: ok=3, missing=1, total=4" in text
    assert "[MISSING] docs/ops_reports/index.html" in text
    assert "## Failed Command Retry Guide" in text
    assert "suggested_retry_command: python -m src.main retention" in text
    assert "runbook_reference: [docs/runbook.md#日次パイプライン](docs/runbook.md#日次パイプライン)" in text
    assert "runbook_reference_anchor: #日次パイプライン" in text


def test_write_ops_reports_index_lists_latest_and_recent(tmp_path):
    out_dir = tmp_path / "docs" / "ops_reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "latest_ops_report.md").write_text("latest md", encoding="utf-8")
    (out_dir / "latest_ops_report.html").write_text("latest html", encoding="utf-8")
    (out_dir / "ops-report-2026-02-01.md").write_text("old md", encoding="utf-8")
    (out_dir / "ops-report-2026-03-01.md").write_text("new md", encoding="utf-8")
    (out_dir / "ops-report-2026-03-01.html").write_text("new html", encoding="utf-8")

    index_path = write_ops_reports_index(output_dir=out_dir, limit=1)
    text = index_path.read_text(encoding="utf-8")

    assert "latest_ops_report.md" in text
    assert "latest_ops_report.html" in text
    assert "ops-report-2026-03-01.md" in text
    assert "ops-report-2026-03-01.html" in text
    assert "ops-report-2026-02-01.md" not in text


def test_write_ops_reports_index_handles_empty_directory(tmp_path):
    out_dir = tmp_path / "docs" / "ops_reports"
    index_path = write_ops_reports_index(output_dir=out_dir, limit=8)
    text = index_path.read_text(encoding="utf-8")

    assert "No ops reports yet." in text

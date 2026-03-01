from datetime import datetime

from src.alerts import parse_alert_line, parse_alert_lines, summarize_alerts


def test_parse_alert_line_extracts_timestamp_pipeline_and_type() -> None:
    parsed = parse_alert_line("[2026-02-28T09:30:00] WARNING daily pipeline: promoted actions below threshold (0 < 1)")

    assert parsed.timestamp == datetime(2026, 2, 28, 9, 30, 0)
    assert parsed.pipeline == "daily"
    assert parsed.alert_type == "threshold"


def test_parse_alert_line_detects_webhook_and_command_failures() -> None:
    webhook = parse_alert_line("[2026-02-28T10:00:00] ERROR weekly pipeline: alert webhook final failure after 3 attempts")
    command = parse_alert_line("[2026-02-28T10:01:00] ERROR daily pipeline: command failed: python -m src.main analyze --ai")
    monthly = parse_alert_line("[2026-03-01T00:00:00] INFO weekly pipeline: monthly report scheduled for 2026-02")

    assert webhook.alert_type == "webhook_failed"
    assert webhook.pipeline == "weekly"
    assert command.alert_type == "command_failed"
    assert monthly.alert_type == "monthly_scheduled"


def test_summarize_alerts_filters_by_since_and_returns_breakdowns() -> None:
    alerts = parse_alert_lines(
        [
            "[2026-02-27T09:30:00] WARNING daily pipeline: promoted actions below threshold (0 < 1)",
            "[2026-02-28T09:30:00] ERROR weekly pipeline: command failed: python -m src.main weekly-report --ai",
            "[2026-02-28T10:00:00] ERROR weekly pipeline: alert webhook final failure after 3 attempts",
            "[2026-02-28T10:05:00] INFO weekly pipeline: monthly report scheduled for 2026-02",
            "invalid line without timestamp",
        ]
    )

    per_day, pipeline_counts, type_counts = summarize_alerts(alerts, since=datetime(2026, 2, 28, 0, 0, 0))

    assert per_day == {"2026-02-28": 3}
    assert pipeline_counts["daily"] == 0
    assert pipeline_counts["weekly"] == 3
    assert pipeline_counts["unknown"] == 0
    assert type_counts["threshold"] == 0
    assert type_counts["command_failed"] == 1
    assert type_counts["webhook_failed"] == 1
    assert type_counts["monthly_scheduled"] == 1
    assert type_counts["other"] == 0

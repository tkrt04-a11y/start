"""Alert log parsing and summarization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re


PIPELINE_CATEGORIES = ("daily", "weekly", "unknown")
ALERT_TYPE_CATEGORIES = ("threshold", "webhook_failed", "command_failed", "monthly_scheduled", "other")

_ALERT_LINE_PATTERN = re.compile(r"^\[(?P<timestamp>[^\]]+)\]\s*(?P<message>.*)$")


@dataclass(frozen=True)
class ParsedAlert:
    """Parsed representation of one alerts.log line."""

    raw_line: str
    message: str
    timestamp: datetime | None
    pipeline: str
    alert_type: str


def _parse_timestamp(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _detect_pipeline(message: str) -> str:
    lower = message.lower()
    if "daily pipeline" in lower or '"pipeline":"daily"' in lower or "pipeline=daily" in lower:
        return "daily"
    if "weekly pipeline" in lower or '"pipeline":"weekly"' in lower or "pipeline=weekly" in lower:
        return "weekly"
    return "unknown"


def _detect_alert_type(message: str) -> str:
    lower = message.lower()
    if "command failed" in lower:
        return "command_failed"
    if "monthly report scheduled" in lower:
        return "monthly_scheduled"
    if "webhook" in lower and ("final failure" in lower or "failed" in lower or "failure" in lower):
        return "webhook_failed"
    if "below threshold" in lower or "threshold" in lower:
        return "threshold"
    return "other"


def parse_alert_line(line: str) -> ParsedAlert:
    match = _ALERT_LINE_PATTERN.match(line.strip())
    if not match:
        message = line.strip()
        return ParsedAlert(
            raw_line=line,
            message=message,
            timestamp=None,
            pipeline=_detect_pipeline(message),
            alert_type=_detect_alert_type(message),
        )

    message = match.group("message").strip()
    return ParsedAlert(
        raw_line=line,
        message=message,
        timestamp=_parse_timestamp(match.group("timestamp")),
        pipeline=_detect_pipeline(message),
        alert_type=_detect_alert_type(message),
    )


def parse_alert_lines(lines: list[str]) -> list[ParsedAlert]:
    return [parse_alert_line(line) for line in lines if line.strip()]


def summarize_alerts(
    alerts: list[ParsedAlert],
    since: datetime,
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    per_day: dict[str, int] = {}
    pipeline_counts: dict[str, int] = {name: 0 for name in PIPELINE_CATEGORIES}
    type_counts: dict[str, int] = {name: 0 for name in ALERT_TYPE_CATEGORIES}

    for alert in alerts:
        if alert.timestamp is None:
            continue
        if alert.timestamp < since:
            continue

        day = alert.timestamp.date().isoformat()
        per_day[day] = per_day.get(day, 0) + 1
        pipeline_counts[alert.pipeline] = pipeline_counts.get(alert.pipeline, 0) + 1
        type_counts[alert.alert_type] = type_counts.get(alert.alert_type, 0) + 1

    return per_day, pipeline_counts, type_counts

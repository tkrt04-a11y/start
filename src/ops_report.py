"""Operational health report generation helpers."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any, Mapping

import markdown

from src.alerts import parse_alert_line
from src.metrics import check_metric_thresholds, normalize_health_summary
from src.schema_versions import SCHEMA_VERSION
from src.ops_report_index import write_ops_reports_index


_PIPELINE_RUN_LOG_PATTERN = re.compile(r"^(daily|weekly|monthly)-run-(\d{8})-(\d{6})\.log$")
_FAILED_COMMAND_PATTERN = re.compile(
    r"^\[(?P<timestamp>[^\]]+)\]\s+ERROR\s+(?P<pipeline>daily|weekly|monthly)\s+pipeline:\s+command failed:\s+(?P<command>.+)$",
    re.IGNORECASE,
)
_RUNBOOK_HEADING_PATTERN = re.compile(r"^#{1,6}\s+(?P<heading>.+?)\s*$")


def _to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _resolve_window_start(days: int, now: datetime) -> datetime:
    if days <= 0:
        return datetime.min
    return now - timedelta(days=days)


def _github_anchor_from_heading(heading: str) -> str:
    normalized = re.sub(r"[\s\t\n\r]+", " ", heading.strip().lower())
    normalized = re.sub(r"[^\w\-\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\s]", "", normalized)
    normalized = normalized.replace(" ", "-")
    normalized = re.sub(r"-+", "-", normalized)
    return normalized.strip("-")


@lru_cache(maxsize=1)
def _load_runbook_heading_by_pipeline(runbook_path: str = "docs/runbook.md") -> dict[str, str]:
    path = Path(runbook_path)
    if not path.exists():
        return {}

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    headings: dict[str, str] = {}
    for line in lines:
        match = _RUNBOOK_HEADING_PATTERN.match(line)
        if not match:
            continue
        heading = match.group("heading").strip()
        lowered = heading.lower()

        if "daily pipeline" in lowered or "日次パイプライン" in heading:
            headings.setdefault("daily", heading)
        elif "weekly pipeline" in lowered or "週次パイプライン" in heading:
            headings.setdefault("weekly", heading)
        elif "monthly pipeline" in lowered or "月次パイプライン" in heading:
            headings.setdefault("monthly", heading)
    return headings


def _collect_top_alert_types(alert_file: Path, since: datetime, top_n: int = 3) -> list[dict[str, Any]]:
    if not alert_file.exists():
        return []

    try:
        lines = [line for line in alert_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return []

    counts: Counter[str] = Counter()
    for line in lines:
        parsed = parse_alert_line(line)
        if parsed.timestamp is None:
            continue
        parsed_ts = _to_naive_utc(parsed.timestamp)
        if parsed_ts < since:
            continue
        counts[parsed.alert_type] += 1

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"type": name, "count": count} for name, count in ranked[: max(0, top_n)]]


def _collect_daily_alert_summaries(logs_dir: Path, since: datetime, limit: int = 7) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(logs_dir.glob("alerts-summary-*.md"), reverse=True):
        if path.name.endswith("-weekly.md"):
            continue

        date_text = path.stem.replace("alerts-summary-", "")
        try:
            summary_date = datetime.strptime(date_text, "%Y%m%d")
        except ValueError:
            continue
        if summary_date < since:
            continue

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue

        command_failures = 0
        alert_count = 0
        alerts: list[str] = []
        in_alerts = False
        for line in lines:
            normalized = line.strip()
            if normalized.startswith("- Command failures:"):
                try:
                    command_failures = int(normalized.split(":", 1)[1].strip())
                except (ValueError, IndexError):
                    command_failures = 0
            elif normalized.startswith("- Alert count:"):
                try:
                    alert_count = int(normalized.split(":", 1)[1].strip())
                except (ValueError, IndexError):
                    alert_count = 0
            elif normalized == "## Alerts":
                in_alerts = True
            elif in_alerts and normalized.startswith("- "):
                alerts.append(normalized[2:].strip())

        rows.append(
            {
                "date": summary_date.date().isoformat(),
                "path": str(path),
                "command_failures": command_failures,
                "alert_count": alert_count,
                "alerts": alerts,
            }
        )
        if len(rows) >= max(0, limit):
            break
    return rows


def _build_runbook_reference_parts(pipeline: str) -> tuple[str, str]:
    runbook_path = "docs/runbook.md"
    heading = _load_runbook_heading_by_pipeline(runbook_path).get(pipeline)
    if not heading:
        return runbook_path, ""

    anchor_slug = _github_anchor_from_heading(heading)
    if not anchor_slug:
        return runbook_path, ""

    anchor = f"#{anchor_slug}"
    return f"{runbook_path}{anchor}", anchor


def _collect_failed_command_retry_guides(logs_dir: Path, since: datetime, limit: int = 12) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(logs_dir.glob("*-run-*.log"), reverse=True):
        match = _PIPELINE_RUN_LOG_PATTERN.match(path.name)
        if not match:
            continue

        pipeline_from_name = match.group(1)
        run_date = match.group(2)
        run_time = match.group(3)
        try:
            file_ts = datetime.strptime(f"{run_date}{run_time}", "%Y%m%d%H%M%S")
        except ValueError:
            continue
        if file_ts < since:
            continue

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue

        for line in lines:
            parsed = _FAILED_COMMAND_PATTERN.match(line.strip())
            if not parsed:
                continue
            failed_command = parsed.group("command").strip()
            if not failed_command:
                continue

            pipeline_name = parsed.group("pipeline").strip().lower() or pipeline_from_name
            event_ts = file_ts
            ts_text = parsed.group("timestamp").strip()
            if ts_text:
                try:
                    candidate = datetime.fromisoformat(ts_text)
                    event_ts = _to_naive_utc(candidate)
                except ValueError:
                    event_ts = file_ts
            if event_ts < since:
                continue

            rows.append(
                {
                    "event_ts": event_ts,
                    "pipeline": pipeline_name,
                    "failed_command": failed_command,
                }
            )

    rows.sort(key=lambda item: item.get("event_ts", datetime.min), reverse=True)

    unique: set[tuple[str, str]] = set()
    guides: list[dict[str, Any]] = []
    for row in rows:
        pipeline_name = str(row.get("pipeline", "")).strip().lower()
        failed_command = str(row.get("failed_command", "")).strip()
        if not pipeline_name or not failed_command:
            continue

        key = (pipeline_name, failed_command)
        if key in unique:
            continue
        unique.add(key)

        runbook_reference, runbook_reference_anchor = _build_runbook_reference_parts(pipeline_name)

        guides.append(
            {
                "pipeline": pipeline_name,
                "failed_command": failed_command,
                "suggested_retry_command": failed_command,
                "runbook_reference": runbook_reference,
                "runbook_reference_anchor": runbook_reference_anchor,
            }
        )
        if len(guides) >= max(0, limit):
            break
    return guides


def _load_artifact_integrity(logs_dir: Path, file_name: str = "weekly-artifact-verify.json") -> dict[str, Any]:
    verify_path = logs_dir / file_name
    default_payload: dict[str, Any] = {
        "source": str(verify_path),
        "ok_count": 0,
        "missing_count": 0,
        "total_count": 0,
        "files": [],
    }
    if not verify_path.exists():
        return default_payload

    try:
        payload = json.loads(verify_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_payload

    if not isinstance(payload, dict):
        return default_payload

    checks = payload.get("checks", [])
    if not isinstance(checks, list):
        checks = []

    files: list[dict[str, str]] = []
    for item in checks:
        if not isinstance(item, dict):
            continue
        relative_path = str(item.get("path", "")).strip()
        status_text = str(item.get("status", "")).strip().upper()
        if not relative_path:
            continue
        status = "OK" if status_text == "OK" else "MISSING"
        files.append({"path": relative_path, "status": status})

    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    ok_count = int(summary.get("ok", sum(1 for item in files if item["status"] == "OK")))
    missing_count = int(summary.get("missing", sum(1 for item in files if item["status"] == "MISSING")))
    total_count = int(summary.get("total", len(files)))

    return {
        "source": str(verify_path),
        "ok_count": max(0, ok_count),
        "missing_count": max(0, missing_count),
        "total_count": max(0, total_count),
        "files": files,
    }


def build_ops_report_data(
    days: int = 7,
    logs_dir: str | Path = "logs",
    now: datetime | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    current = now or datetime.now()
    normalized_days = max(0, int(days))
    window_start = _resolve_window_start(normalized_days, current)

    threshold_result = check_metric_thresholds(days=normalized_days, logs_dir=logs_dir, env=env)
    health_payload = normalize_health_summary(
        threshold_result.get("health") if isinstance(threshold_result.get("health"), Mapping) else None
    )
    summary = threshold_result.get("summary", {}) if isinstance(threshold_result.get("summary"), dict) else {}
    pipelines = summary.get("pipelines", {}) if isinstance(summary.get("pipelines"), dict) else {}

    success_rates: dict[str, dict[str, Any]] = {}
    for pipeline_name in sorted(pipelines.keys()):
        pipeline_item = pipelines.get(pipeline_name, {})
        if not isinstance(pipeline_item, dict):
            continue
        runs = int(pipeline_item.get("runs", 0))
        success_rate = float(pipeline_item.get("success_rate", 0.0))
        success_rates[pipeline_name] = {
            "runs": runs,
            "success_rate": success_rate,
        }

    violations = threshold_result.get("violations", [])
    if not isinstance(violations, list):
        violations = []

    violations_by_pipeline: dict[str, int] = {}
    for violation in violations:
        if not isinstance(violation, dict):
            continue
        pipeline_name = str(violation.get("pipeline", "unknown"))
        violations_by_pipeline[pipeline_name] = violations_by_pipeline.get(pipeline_name, 0) + 1

    top_alert_types = _collect_top_alert_types(Path(logs_dir) / "alerts.log", since=window_start, top_n=3)
    daily_alert_summaries = _collect_daily_alert_summaries(Path(logs_dir), since=window_start, limit=7)
    failed_command_retry_guides = _collect_failed_command_retry_guides(Path(logs_dir), since=window_start, limit=12)
    artifact_integrity = _load_artifact_integrity(Path(logs_dir))

    totals = summary.get("totals", {}) if isinstance(summary.get("totals"), dict) else {}
    recent_command_failures = int(totals.get("command_failures", 0))

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": current.isoformat(timespec="seconds"),
        "days": normalized_days,
        "window_start": window_start.isoformat(timespec="seconds") if normalized_days > 0 else None,
        "total_runs": int(summary.get("total_runs", 0)),
        "health_score": int(health_payload.get("health_score", 0)),
        "health_breakdown": health_payload.get("health_breakdown", {}),
        "pipeline_success_rates": success_rates,
        "threshold_violations_count": len(violations),
        "threshold_violations_by_pipeline": violations_by_pipeline,
        "top_alert_types": top_alert_types,
        "daily_alert_summaries": daily_alert_summaries,
        "artifact_integrity": artifact_integrity,
        "recent_command_failures": recent_command_failures,
        "failed_command_retry_guides": failed_command_retry_guides,
    }


def render_ops_report_markdown(report: Mapping[str, Any]) -> str:
    report_date = datetime.now().date().isoformat()
    generated_at = str(report.get("generated_at", "")).strip()
    if generated_at:
        try:
            report_date = datetime.fromisoformat(generated_at).date().isoformat()
        except ValueError:
            pass

    days = int(report.get("days", 7))
    window_start = report.get("window_start")

    lines: list[str] = []
    lines.append(f"# Ops Report ({report_date})")
    lines.append("")
    lines.append(f"Generated: {generated_at or datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("## Window")
    lines.append(f"- Days: {days}")
    if window_start:
        lines.append(f"- Window start: {window_start}")
    lines.append(f"- Total runs: {int(report.get('total_runs', 0))}")
    lines.append("")

    lines.append("## Health")
    lines.append(f"- health_score: {int(report.get('health_score', 0))}")
    health_breakdown = report.get("health_breakdown", {})
    factors = health_breakdown.get("factors", {}) if isinstance(health_breakdown, dict) else {}
    penalties = health_breakdown.get("penalties", {}) if isinstance(health_breakdown, dict) else {}
    formula = health_breakdown.get("formula", "") if isinstance(health_breakdown, dict) else ""
    lines.append("- health_breakdown:")
    lines.append(
        "  - factors: "
        f"avg_success_rate={float(factors.get('average_pipeline_success_rate', 0.0)):.4f}, "
        f"violation_count={int(factors.get('violation_count', 0))}, "
        f"command_failures={int(factors.get('command_failures', 0))}, "
        f"alert_count={int(factors.get('alert_count', 0))}"
    )
    lines.append(
        "  - penalties: "
        f"success_rate={float(penalties.get('success_rate', 0.0)):.4f}, "
        f"violations={float(penalties.get('violations', 0.0)):.4f}, "
        f"command_failures={float(penalties.get('command_failures', 0.0)):.4f}, "
        f"alerts={float(penalties.get('alerts', 0.0)):.4f}"
    )
    lines.append(f"  - formula: {formula}")
    lines.append("")

    lines.append("## Pipeline Success Rate")
    pipeline_success_rates = report.get("pipeline_success_rates", {})
    if isinstance(pipeline_success_rates, dict) and pipeline_success_rates:
        for pipeline_name in sorted(pipeline_success_rates.keys()):
            item = pipeline_success_rates.get(pipeline_name, {})
            if not isinstance(item, dict):
                continue
            runs = int(item.get("runs", 0))
            success_rate = float(item.get("success_rate", 0.0)) * 100
            lines.append(f"- {pipeline_name}: runs={runs}, success_rate={success_rate:.1f}%")
    else:
        lines.append("- No pipeline metrics in window")
    lines.append("")

    lines.append("## Threshold Violations")
    total_violations = int(report.get("threshold_violations_count", 0))
    lines.append(f"- Total violations: {total_violations}")
    violations_by_pipeline = report.get("threshold_violations_by_pipeline", {})
    if isinstance(violations_by_pipeline, dict) and violations_by_pipeline:
        for pipeline_name in sorted(violations_by_pipeline.keys()):
            lines.append(f"- {pipeline_name}: {int(violations_by_pipeline[pipeline_name])}")
    lines.append("")

    lines.append("## Top Alert Types")
    top_alert_types = report.get("top_alert_types", [])
    if isinstance(top_alert_types, list) and top_alert_types:
        for item in top_alert_types:
            if not isinstance(item, dict):
                continue
            alert_type = str(item.get("type", "other"))
            count = int(item.get("count", 0))
            lines.append(f"- {alert_type}: {count}")
    else:
        lines.append("- No alerts in window")
    lines.append("")

    lines.append("## Daily Alert Summaries")
    daily_alert_summaries = report.get("daily_alert_summaries", [])
    if isinstance(daily_alert_summaries, list) and daily_alert_summaries:
        for item in daily_alert_summaries:
            if not isinstance(item, dict):
                continue
            summary_date = str(item.get("date", ""))
            command_failures = int(item.get("command_failures", 0))
            alert_count = int(item.get("alert_count", 0))
            lines.append(f"- {summary_date}: command_failures={command_failures}, alert_count={alert_count}")
            alerts = item.get("alerts", [])
            if isinstance(alerts, list):
                for alert_line in alerts[:3]:
                    lines.append(f"  - {str(alert_line)}")
    else:
        lines.append("- No daily alert summaries in window")
    lines.append("")

    lines.append("## Artifact Integrity")
    artifact_integrity = report.get("artifact_integrity", {})
    if isinstance(artifact_integrity, dict):
        source = str(artifact_integrity.get("source", "")).strip()
        ok_count = int(artifact_integrity.get("ok_count", 0))
        missing_count = int(artifact_integrity.get("missing_count", 0))
        total_count = int(artifact_integrity.get("total_count", 0))
        if source:
            lines.append(f"- Source: {source}")
        lines.append(f"- Summary: ok={ok_count}, missing={missing_count}, total={total_count}")
        files = artifact_integrity.get("files", [])
        if isinstance(files, list) and files:
            for item in files:
                if not isinstance(item, dict):
                    continue
                path_text = str(item.get("path", "")).strip()
                status_text = str(item.get("status", "")).strip().upper()
                if not path_text:
                    continue
                status = "OK" if status_text == "OK" else "MISSING"
                lines.append(f"- [{status}] {path_text}")
        else:
            lines.append("- No verification rows")
    else:
        lines.append("- No artifact integrity data")
    lines.append("")

    lines.append("## Command Failures")
    lines.append(f"- Recent command failures: {int(report.get('recent_command_failures', 0))}")
    lines.append("")

    lines.append("## Failed Command Retry Guide")
    failed_guides = report.get("failed_command_retry_guides", [])
    if isinstance(failed_guides, list) and failed_guides:
        for item in failed_guides:
            if not isinstance(item, dict):
                continue
            pipeline_name = str(item.get("pipeline", ""))
            failed_command = str(item.get("failed_command", ""))
            retry_command = str(item.get("suggested_retry_command", ""))
            runbook_reference = str(item.get("runbook_reference", ""))
            runbook_reference_anchor = str(item.get("runbook_reference_anchor", ""))
            lines.append(f"- pipeline={pipeline_name}")
            lines.append(f"  - failed_command: {failed_command}")
            lines.append(f"  - suggested_retry_command: {retry_command}")
            if runbook_reference:
                lines.append(f"  - runbook_reference: [{runbook_reference}]({runbook_reference})")
            else:
                lines.append("  - runbook_reference: ")
            lines.append(f"  - runbook_reference_anchor: {runbook_reference_anchor}")
    else:
        lines.append("- No failed commands in window")
    lines.append("")

    return "\n".join(lines)


def write_ops_report(
    report: Mapping[str, Any],
    output_dir: str | Path = "docs/ops_reports",
) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    generated_at = str(report.get("generated_at", "")).strip()
    if generated_at:
        try:
            report_date = datetime.fromisoformat(generated_at).date()
        except ValueError:
            report_date = datetime.now().date()
    else:
        report_date = datetime.now().date()

    label = report_date.isoformat()
    text = render_ops_report_markdown(report)

    report_path = out_dir / f"ops-report-{label}.md"
    report_path.write_text(text, encoding="utf-8")

    latest_path = out_dir / "latest_ops_report.md"
    latest_path.write_text(text, encoding="utf-8")

    html_body = markdown.markdown(text)
    html_doc = (
        "<!DOCTYPE html>\n"
        "<html lang=\"ja\">\n"
        "<head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        "<title>Ops Report</title></head>\n"
        f"<body>{html_body}</body>\n"
        "</html>\n"
    )

    report_html_path = out_dir / f"ops-report-{label}.html"
    report_html_path.write_text(html_doc, encoding="utf-8")

    latest_html_path = out_dir / "latest_ops_report.html"
    latest_html_path.write_text(html_doc, encoding="utf-8")

    write_ops_reports_index(output_dir=out_dir)

    return report_path


def generate_and_write_ops_report(days: int = 7, logs_dir: str | Path = "logs") -> tuple[dict[str, Any], Path]:
    report = build_ops_report_data(days=days, logs_dir=logs_dir)
    path = write_ops_report(report)
    return report, path

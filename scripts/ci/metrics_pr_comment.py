from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MARKER = "<!-- ai-starter:metrics-check -->"
_PIPELINES = ("daily", "weekly", "monthly")


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_number(value: Any) -> str:
    parsed = _to_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:.6g}"


def _iter_threshold_rows(payload: dict[str, Any]) -> list[tuple[str, str, str]]:
    raw_thresholds = payload.get("thresholds", {})
    thresholds = raw_thresholds if isinstance(raw_thresholds, dict) else {}
    rows: list[tuple[str, str, str]] = []
    for pipeline in _PIPELINES:
        item = thresholds.get(pipeline, {})
        threshold_set = item if isinstance(item, dict) else {}
        duration = _format_number(threshold_set.get("max_duration_sec"))
        failure_rate = _format_number(threshold_set.get("max_failure_rate"))
        rows.append((pipeline, duration, failure_rate))
    return rows


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_violations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_violations = payload.get("violations", [])
    return [item for item in raw_violations if isinstance(item, dict)] if isinstance(raw_violations, list) else []


def _extract_health_score(payload: dict[str, Any]) -> int | None:
    direct = payload.get("health_score")
    if isinstance(direct, bool):
        return int(direct)
    if isinstance(direct, (int, float)):
        return int(direct)
    health = _as_dict(payload.get("health"))
    score = health.get("score")
    if isinstance(score, bool):
        return int(score)
    if isinstance(score, (int, float)):
        return int(score)
    return None


def _count_violations_by_pipeline(violations: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {pipeline: 0 for pipeline in _PIPELINES}
    for item in violations:
        pipeline = str(item.get("pipeline", "")).strip().lower()
        if pipeline in counts:
            counts[pipeline] += 1
    return counts


def _format_delta(current: int | None, previous: int | None) -> str:
    if current is None or previous is None:
        return "n/a"
    delta = current - previous
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta}"


def _format_int_or_na(value: int | None) -> str:
    if value is None:
        return "n/a"
    return str(value)


def _extract_retry_guides(ops_report_payload: dict[str, Any] | None) -> list[dict[str, str]]:
    if not isinstance(ops_report_payload, dict):
        return []
    raw_guides = ops_report_payload.get("failed_command_retry_guides", [])
    if not isinstance(raw_guides, list):
        return []

    guides: list[dict[str, str]] = []
    for item in raw_guides:
        if not isinstance(item, dict):
            continue
        pipeline = str(item.get("pipeline", "")).strip()
        suggested_retry_command = str(item.get("suggested_retry_command", "")).strip()
        runbook_reference = str(item.get("runbook_reference", "")).strip()
        if not pipeline and not suggested_retry_command and not runbook_reference:
            continue
        guides.append(
            {
                "pipeline": pipeline or "n/a",
                "suggested_retry_command": suggested_retry_command or "n/a",
                "runbook_reference": runbook_reference or "n/a",
            }
        )
    return guides


def _as_markdown_link_or_text(value: str) -> str:
    if value == "n/a":
        return value
    return f"[{value}]({value})"


def build_comment(
    payload: dict[str, Any],
    previous_payload: dict[str, Any] | None = None,
    ops_report_payload: dict[str, Any] | None = None,
) -> str:
    days = int(payload.get("days", 30))
    threshold_profile = str(payload.get("threshold_profile", "prod"))
    violations = _extract_violations(payload)

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    lines: list[str] = [MARKER, "## Metrics Check", ""]
    lines.append(f"- Window: last {days} days")
    lines.append(f"- Threshold profile: `{threshold_profile}`")
    lines.append("- Effective thresholds (resolved)")
    lines.append("")
    lines.append("| Pipeline | Max duration (sec) | Max failure rate |")
    lines.append("|---|---:|---:|")
    for pipeline, duration, failure_rate in _iter_threshold_rows(payload):
        lines.append(f"| {pipeline} | {duration} | {failure_rate} |")

    if violations:
        lines.append(f"- Status: ❌ violations detected ({len(violations)})")
        lines.append("")
        lines.append("| Pipeline | Metric | Threshold | Observed |")
        lines.append("|---|---|---:|---:|")
        for item in violations:
            if not isinstance(item, dict):
                continue
            pipeline = str(item.get("pipeline", "unknown"))
            metric = str(item.get("metric", "unknown"))
            threshold = _format_number(item.get("threshold"))
            observed = _format_number(item.get("observed"))
            lines.append(f"| {pipeline} | {metric} | {threshold} | {observed} |")
    else:
        lines.append("- Status: ✅ pass (no threshold violations)")

    lines.append("")
    lines.append("### Comparison with previous result")
    if isinstance(previous_payload, dict):
        previous_violations = _extract_violations(previous_payload)
        current_violation_count = len(violations)
        previous_violation_count = len(previous_violations)
        current_health_score = _extract_health_score(payload)
        previous_health_score = _extract_health_score(previous_payload)
        current_pipeline_counts = _count_violations_by_pipeline(violations)
        previous_pipeline_counts = _count_violations_by_pipeline(previous_violations)

        lines.append("")
        lines.append("| Metric | Previous | Current | Delta |")
        lines.append("|---|---:|---:|---:|")
        lines.append(
            "| violation_count | "
            f"{previous_violation_count} | {current_violation_count} | "
            f"{_format_delta(current_violation_count, previous_violation_count)} |"
        )
        lines.append(
            "| health_score | "
            f"{_format_int_or_na(previous_health_score)} | { _format_int_or_na(current_health_score)} | "
            f"{_format_delta(current_health_score, previous_health_score)} |"
        )
        for pipeline in _PIPELINES:
            current_count = current_pipeline_counts.get(pipeline, 0)
            previous_count = previous_pipeline_counts.get(pipeline, 0)
            lines.append(
                f"| {pipeline}.violation_count | {previous_count} | {current_count} | "
                f"{_format_delta(current_count, previous_count)} |"
            )
    else:
        lines.append("- Previous result not found or unreadable; comparison skipped.")

    lines.append("")
    lines.append("### Runbook reference and retry guide")
    retry_guides = _extract_retry_guides(ops_report_payload)
    if retry_guides:
        lines.append("")
        lines.append("| Pipeline | Suggested retry command | Runbook reference |")
        lines.append("|---|---|---|")
        for guide in retry_guides:
            pipeline = guide["pipeline"]
            suggested_retry_command = guide["suggested_retry_command"]
            runbook_reference = _as_markdown_link_or_text(guide["runbook_reference"])
            lines.append(f"| {pipeline} | {suggested_retry_command} | {runbook_reference} |")
    else:
        lines.append(
            "- Retry guide unavailable: `failed_command_retry_guides` was not found or was empty in `logs/ops-report-ci.json`."
        )

    lines.append("")
    lines.append(f"_Updated at: {generated_at}_")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", dest="input_path", required=True)
    parser.add_argument("--output", dest="output_path", required=True)
    parser.add_argument("--previous", dest="previous_path", required=False, default="")
    parser.add_argument("--ops-report", dest="ops_report_path", required=False, default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_path)
    output_path = Path(args.output_path)
    previous_path = Path(args.previous_path) if args.previous_path else None
    ops_report_path = Path(args.ops_report_path) if args.ops_report_path else None

    payload: dict[str, Any] = {"days": 30, "threshold_profile": "prod", "violations": []}
    if input_path.exists():
        try:
            loaded = json.loads(input_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except json.JSONDecodeError:
            payload = {
                "days": 30,
                "threshold_profile": "unknown",
                "violations": [],
            }

    previous_payload: dict[str, Any] | None = None
    if previous_path and previous_path.exists():
        try:
            loaded_previous = json.loads(previous_path.read_text(encoding="utf-8"))
            if isinstance(loaded_previous, dict):
                previous_payload = loaded_previous
        except json.JSONDecodeError:
            previous_payload = None

    ops_report_payload: dict[str, Any] | None = None
    if ops_report_path and ops_report_path.exists():
        try:
            loaded_ops_report = json.loads(ops_report_path.read_text(encoding="utf-8"))
            if isinstance(loaded_ops_report, dict):
                ops_report_payload = loaded_ops_report
        except json.JSONDecodeError:
            ops_report_payload = None

    output_path.write_text(
        build_comment(payload, previous_payload=previous_payload, ops_report_payload=ops_report_payload), encoding="utf-8"
    )


if __name__ == "__main__":
    main()

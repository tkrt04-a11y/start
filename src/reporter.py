"""Weekly report generation utilities."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import re
from typing import Iterable

import markdown


def _parse_collected_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def filter_entries_by_days(
    entries: Iterable[dict],
    days: int,
    include_missing_timestamp: bool = True,
    now: datetime | None = None,
) -> list[dict]:
    """Filter entries to those collected within the last ``days`` days."""
    if days <= 0:
        return list(entries)

    current = now or datetime.now()
    cutoff = current - timedelta(days=days)

    filtered: list[dict] = []
    for entry in entries:
        parsed = _parse_collected_at(entry.get("collected_at"))
        if not parsed:
            if include_missing_timestamp:
                filtered.append(entry)
            continue

        if parsed >= cutoff:
            filtered.append(entry)
    return filtered


def filter_entries_between(
    entries: Iterable[dict],
    start_inclusive: datetime,
    end_exclusive: datetime,
    include_missing_timestamp: bool = False,
) -> list[dict]:
    """Filter entries in [start_inclusive, end_exclusive)."""
    filtered: list[dict] = []
    for entry in entries:
        parsed = _parse_collected_at(entry.get("collected_at"))
        if not parsed:
            if include_missing_timestamp:
                filtered.append(entry)
            continue
        if start_inclusive <= parsed < end_exclusive:
            filtered.append(entry)
    return filtered


def compute_source_deltas(
    current_summary: dict[str, int],
    previous_summary: dict[str, int],
) -> dict[str, int]:
    """Compute source count deltas (current - previous)."""
    deltas: dict[str, int] = {}
    keys = set(current_summary) | set(previous_summary)
    for key in keys:
        deltas[key] = current_summary.get(key, 0) - previous_summary.get(key, 0)
    return deltas


def top_delta_sources(deltas: dict[str, int], limit: int = 3) -> list[tuple[str, int]]:
    """Return top sources by absolute delta."""
    ranked = sorted(deltas.items(), key=lambda item: abs(item[1]), reverse=True)
    return ranked[: max(0, limit)]


def recommend_action_for_source(source: str, delta: int) -> str:
    """Generate a concise recommendation for a spotlight source."""
    increasing = delta >= 0

    if source.startswith("github:"):
        if increasing:
            return "Review top issues and convert recurring requests into template tasks."
        return "Check resolved issues and update docs/tests to lock in improvements."

    if source.startswith("rss:"):
        if increasing:
            return "Summarize trend topics and map them to next starter-kit experiments."
        return "Reassess feed relevance and keep only high-signal sources."

    if source.startswith("survey"):
        if increasing:
            return "Translate user feedback spikes into prioritized backlog items."
        return "Validate whether earlier survey pain points have been addressed."

    if increasing:
        return "Create one concrete improvement item and assign an owner."
    return "Monitor this signal and adjust collection strategy if needed."


def infer_priority_from_delta(delta: int) -> str:
    """Infer action priority label from period-over-period delta magnitude."""
    magnitude = abs(delta)
    if magnitude >= 20:
        return "High"
    if magnitude >= 5:
        return "Med"
    return "Low"


def extract_spotlight_action_items_from_markdown(markdown_text: str, limit: int = 5) -> list[dict[str, str]]:
    """Extract action and inferred priority from weekly report Spotlight bullets."""
    items: list[dict[str, str]] = []
    in_spotlight = False
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            in_spotlight = line == "## Spotlight (Top 3 Changes)"
            continue
        if not in_spotlight:
            continue
        if "| Action:" not in line:
            continue

        left, action_part = line.split("| Action:", 1)
        action = action_part.strip()
        if not action:
            continue

        delta = 0
        match = re.search(r":\s*([+-]?\d+)\s*$", left)
        if match:
            delta = int(match.group(1))

        items.append({"action": action, "priority": infer_priority_from_delta(delta)})
        if len(items) >= limit:
            break
    return items


def extract_spotlight_actions_from_markdown(markdown_text: str, limit: int = 5) -> list[str]:
    """Extract `Action:` entries from the Spotlight section of weekly report markdown."""
    return [item["action"] for item in extract_spotlight_action_items_from_markdown(markdown_text, limit=limit)]


def extract_promoted_actions_from_markdown(markdown_text: str, limit: int = 5) -> list[str]:
    """Extract `[Promoted]` action items from weekly report markdown."""
    actions: list[str] = []
    in_action_items = False
    prefix = "- [ ] [Promoted] "

    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            in_action_items = line == "## Action Items"
            continue
        if not in_action_items:
            continue
        if line.startswith(prefix):
            action = line[len(prefix):].strip()
            if action:
                actions.append(action)
        if len(actions) >= limit:
            break
    return actions


def extract_monthly_promoted_actions_from_markdown(markdown_text: str, limit: int = 5) -> list[str]:
    """Extract monthly `[Promoted]` action items from monthly report markdown."""
    actions: list[str] = []
    in_promotable_actions = False
    prefix = "- [ ] [Promoted] "

    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            in_promotable_actions = line == "## Promotable Actions"
            continue
        if not in_promotable_actions:
            continue
        if line.startswith(prefix):
            action = line[len(prefix):].strip()
            if action:
                actions.append(action)
        if len(actions) >= limit:
            break
    return actions


def _current_week_label(today: date | None = None) -> str:
    d = today or date.today()
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _current_month_label(today: date | None = None) -> str:
    d = today or date.today()
    return f"{d.year:04d}-{d.month:02d}"


def _previous_month_label(month_label: str) -> str | None:
    try:
        month_start = datetime.strptime(month_label, "%Y-%m")
    except ValueError:
        return None

    if month_start.month == 1:
        return f"{month_start.year - 1:04d}-12"
    return f"{month_start.year:04d}-{month_start.month - 1:02d}"


def generate_weekly_report_markdown(
    entries: Iterable[dict],
    source_summary: dict[str, int],
    ai_summary: str = "",
    previous_summary: dict[str, int] | None = None,
    period_days: int | None = None,
    today: date | None = None,
) -> str:
    """Generate markdown content for weekly report."""
    entry_list = list(entries)
    week_label = _current_week_label(today)

    lines: list[str] = []
    promoted_actions: list[str] = []
    lines.append(f"# Weekly Report ({week_label})")
    lines.append("")
    lines.append(f"Generated: {(today or date.today()).isoformat()}")
    lines.append("")
    lines.append("## Overview")
    lines.append(f"- Total entries: {len(entry_list)}")
    lines.append(f"- Unique sources: {len(source_summary)}")
    lines.append("")
    lines.append("## Source Breakdown")
    if source_summary:
        for source, count in sorted(source_summary.items(), key=lambda item: item[1], reverse=True):
            lines.append(f"- {source}: {count}")
    else:
        lines.append("- No data")
    lines.append("")
    if previous_summary is not None and period_days and period_days > 0:
        deltas = compute_source_deltas(source_summary, previous_summary)
        lines.append(f"## Period-over-Period Delta (vs previous {period_days} days)")
        if deltas:
            for source, delta in sorted(deltas.items(), key=lambda item: abs(item[1]), reverse=True):
                sign = "+" if delta >= 0 else ""
                lines.append(f"- {source}: {sign}{delta}")
        else:
            lines.append("- No comparable timestamped data")
        lines.append("")

        lines.append("## Spotlight (Top 3 Changes)")
        spotlight = top_delta_sources(deltas, limit=3)
        if spotlight:
            for source, delta in spotlight:
                sign = "+" if delta >= 0 else ""
                action = recommend_action_for_source(source, delta)
                lines.append(f"- {source}: {sign}{delta} | Action: {action}")
                if infer_priority_from_delta(delta) == "High":
                    promoted_actions.append(action)
        else:
            lines.append("- No major change detected")
        lines.append("")

    lines.append("## AI / Heuristic Summary")
    lines.append(ai_summary.strip() if ai_summary.strip() else "- No summary available")
    lines.append("")
    lines.append("## Action Items")
    if promoted_actions:
        for action in dict.fromkeys(promoted_actions):
            lines.append(f"- [ ] [Promoted] {action}")
    lines.append("- [ ] Promote top weekly finding into starter template")
    lines.append("- [ ] Add one test for recurring issue pattern")
    lines.append("- [ ] Improve docs for top confusion signal")
    lines.append("")
    return "\n".join(lines)


def write_weekly_report(
    entries: Iterable[dict],
    source_summary: dict[str, int],
    ai_summary: str = "",
    previous_summary: dict[str, int] | None = None,
    period_days: int | None = None,
    output_dir: Path | str = "docs/weekly_reports",
    today: date | None = None,
) -> Path:
    """Write weekly report markdown and update latest pointer."""
    week_label = _current_week_label(today)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report_path = out_dir / f"weekly-report-{week_label}.md"
    text = generate_weekly_report_markdown(
        entries,
        source_summary,
        ai_summary=ai_summary,
        previous_summary=previous_summary,
        period_days=period_days,
        today=today,
    )
    report_path.write_text(text, encoding="utf-8")

    latest_path = out_dir / "latest_weekly_report.md"
    latest_path.write_text(text, encoding="utf-8")

    html_body = markdown.markdown(text)
    html_doc = (
        "<!DOCTYPE html>\n"
        "<html lang=\"ja\">\n"
        "<head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        "<title>Weekly Report</title></head>\n"
        f"<body>{html_body}</body>\n"
        "</html>\n"
    )

    report_html_path = out_dir / f"weekly-report-{week_label}.html"
    report_html_path.write_text(html_doc, encoding="utf-8")

    latest_html_path = out_dir / "latest_weekly_report.html"
    latest_html_path.write_text(html_doc, encoding="utf-8")
    return report_path


def generate_monthly_report_markdown(
    entries: Iterable[dict],
    source_summary: dict[str, int],
    ai_summary: str = "",
    previous_summary: dict[str, int] | None = None,
    month_label: str | None = None,
    today: date | None = None,
) -> str:
    """Generate markdown content for monthly report."""
    entry_list = list(entries)
    label = month_label or _current_month_label(today)

    lines: list[str] = []
    promoted_actions: list[str] = []
    lines.append(f"# Monthly Report ({label})")
    lines.append("")
    lines.append(f"Generated: {(today or date.today()).isoformat()}")
    lines.append("")
    lines.append("## Overview")
    lines.append(f"- Target month: {label}")
    lines.append(f"- Total entries: {len(entry_list)}")
    lines.append(f"- Unique sources: {len(source_summary)}")
    lines.append("")
    lines.append("## Source Breakdown")
    if source_summary:
        for source, count in sorted(source_summary.items(), key=lambda item: item[1], reverse=True):
            lines.append(f"- {source}: {count}")
    else:
        lines.append("- No data")
    lines.append("")
    if previous_summary is not None:
        deltas = compute_source_deltas(source_summary, previous_summary)
        previous_label = _previous_month_label(label)
        if previous_label:
            lines.append(f"## Period-over-Period Delta (vs previous month: {previous_label})")
        else:
            lines.append("## Period-over-Period Delta (vs previous month)")
        if deltas:
            for source, delta in sorted(deltas.items(), key=lambda item: abs(item[1]), reverse=True):
                sign = "+" if delta >= 0 else ""
                lines.append(f"- {source}: {sign}{delta}")
        else:
            lines.append("- No comparable timestamped data")
        lines.append("")

        lines.append("## Spotlight (Top 3 Changes)")
        spotlight = top_delta_sources(deltas, limit=3)
        if spotlight:
            for source, delta in spotlight:
                sign = "+" if delta >= 0 else ""
                action = recommend_action_for_source(source, delta)
                lines.append(f"- {source}: {sign}{delta} | Action: {action}")
                if infer_priority_from_delta(delta) == "High":
                    promoted_actions.append(action)
        else:
            lines.append("- No major change detected")
        lines.append("")

    if promoted_actions:
        lines.append("## Promotable Actions")
        for action in dict.fromkeys(promoted_actions):
            lines.append(f"- [ ] [Promoted] {action}")
        lines.append("")

    lines.append("## AI / Heuristic Summary")
    lines.append(ai_summary.strip() if ai_summary.strip() else "- No summary available")
    lines.append("")
    lines.append("## Action Items")
    lines.append("- [ ] Promote top monthly finding into starter template")
    lines.append("- [ ] Add one regression test for recurring monthly trend")
    lines.append("- [ ] Update docs based on monthly top signals")
    lines.append("")
    return "\n".join(lines)


def write_monthly_report(
    entries: Iterable[dict],
    source_summary: dict[str, int],
    ai_summary: str = "",
    previous_summary: dict[str, int] | None = None,
    month_label: str | None = None,
    output_dir: Path | str = "docs/monthly_reports",
    today: date | None = None,
) -> Path:
    """Write monthly report markdown and update latest pointer."""
    label = month_label or _current_month_label(today)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report_path = out_dir / f"monthly-report-{label}.md"
    text = generate_monthly_report_markdown(
        entries,
        source_summary,
        ai_summary=ai_summary,
        previous_summary=previous_summary,
        month_label=label,
        today=today,
    )
    report_path.write_text(text, encoding="utf-8")

    latest_path = out_dir / "latest_monthly_report.md"
    latest_path.write_text(text, encoding="utf-8")

    html_body = markdown.markdown(text)
    html_doc = (
        "<!DOCTYPE html>\n"
        "<html lang=\"ja\">\n"
        "<head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        "<title>Monthly Report</title></head>\n"
        f"<body>{html_body}</body>\n"
        "</html>\n"
    )

    report_html_path = out_dir / f"monthly-report-{label}.html"
    report_html_path.write_text(html_doc, encoding="utf-8")

    latest_html_path = out_dir / "latest_monthly_report.html"
    latest_html_path.write_text(html_doc, encoding="utf-8")
    return report_path

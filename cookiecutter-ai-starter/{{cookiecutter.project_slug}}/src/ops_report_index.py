"""Ops report static index generation helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re


OPS_REPORT_FILE_PATTERN = re.compile(r"^ops-report-(\d{4}-\d{2}-\d{2})\.(md|html)$")


def _collect_report_rows(ops_reports_dir: Path) -> list[dict[str, str | None]]:
    rows: dict[str, dict[str, str | None]] = {}
    for item in ops_reports_dir.glob("ops-report-*.md"):
        match = OPS_REPORT_FILE_PATTERN.match(item.name)
        if not match:
            continue
        label = match.group(1)
        row = rows.get(label, {"date": label, "md": None, "html": None})
        row["md"] = item.name
        rows[label] = row

    for item in ops_reports_dir.glob("ops-report-*.html"):
        match = OPS_REPORT_FILE_PATTERN.match(item.name)
        if not match:
            continue
        label = match.group(1)
        row = rows.get(label, {"date": label, "md": None, "html": None})
        row["html"] = item.name
        rows[label] = row

    return [rows[key] for key in sorted(rows.keys(), reverse=True)]


def render_ops_reports_index(rows: list[dict[str, str | None]], limit: int = 8) -> str:
    normalized_limit = max(1, int(limit))
    generated_at = datetime.now().isoformat(timespec="seconds")

    latest_md = "latest_ops_report.md"
    latest_html = "latest_ops_report.html"

    lines: list[str] = []
    lines.append("<!DOCTYPE html>")
    lines.append('<html lang="ja">')
    lines.append("<head>")
    lines.append('  <meta charset="UTF-8">')
    lines.append('  <meta name="viewport" content="width=device-width, initial-scale=1.0">')
    lines.append("  <title>Ops Reports</title>")
    lines.append("  <style>")
    lines.append(
        "    body { font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, \"Helvetica Neue\", Arial, sans-serif; margin: 2rem; line-height: 1.6; }"
    )
    lines.append("    h1, h2 { color: #333; }")
    lines.append("    ul { padding-left: 1.2rem; }")
    lines.append("    li { margin: 0.3rem 0; }")
    lines.append("  </style>")
    lines.append("</head>")
    lines.append("<body>")
    lines.append("  <h1>Ops Reports</h1>")
    lines.append(f"  <p>Generated: {generated_at}</p>")
    lines.append("  <h2>Latest</h2>")
    lines.append("  <ul>")
    lines.append(f'    <li><a href="{latest_md}">latest_ops_report.md</a></li>')
    lines.append(f'    <li><a href="{latest_html}">latest_ops_report.html</a></li>')
    lines.append("  </ul>")
    lines.append("  <h2>Recent Reports</h2>")
    if rows:
        lines.append("  <ul>")
        for row in rows[:normalized_limit]:
            date_label = str(row.get("date") or "")
            md_name = row.get("md")
            html_name = row.get("html")
            link_parts: list[str] = []
            if md_name:
                link_parts.append(f'<a href="{md_name}">md</a>')
            if html_name:
                link_parts.append(f'<a href="{html_name}">html</a>')
            links = " / ".join(link_parts) if link_parts else "(no files)"
            lines.append(f"    <li>{date_label}: {links}</li>")
        lines.append("  </ul>")
    else:
        lines.append("  <p>No ops reports yet.</p>")
    lines.append("</body>")
    lines.append("</html>")
    lines.append("")
    return "\n".join(lines)


def write_ops_reports_index(output_dir: str | Path = "docs/ops_reports", limit: int = 8) -> Path:
    ops_reports_dir = Path(output_dir)
    ops_reports_dir.mkdir(parents=True, exist_ok=True)

    rows = _collect_report_rows(ops_reports_dir)
    content = render_ops_reports_index(rows, limit=limit)

    index_path = ops_reports_dir / "index.html"
    index_path.write_text(content, encoding="utf-8")
    return index_path

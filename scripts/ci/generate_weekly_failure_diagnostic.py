from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_REQUIRED_FILES = (
    "docs/ops_reports/latest_ops_report.md",
    "docs/ops_reports/latest_ops_report.html",
    "docs/ops_reports/index.html",
    "logs/ops-report-ci.json",
)

DEFAULT_COMMANDS = (
    "python -m pip install --upgrade pip",
    "pip install -r requirements.txt",
    "python -m src.main ops-report --days 7 --json > logs/ops-report-ci.json",
    "Copy-Item logs/ops-report-ci.json logs/ops-report-weekly.json -Force",
    "python -m src.main ops-report-index --limit 8",
    "python scripts/ci/verify_weekly_ops_artifacts.py --json-output logs/weekly-artifact-verify.json",
)


def missing_required_files(required_files: list[str], root: Path) -> list[str]:
    return [path for path in required_files if not (root / path).is_file()]


def parse_outcome_pairs(pairs: list[str] | None) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    for pair in pairs or []:
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            outcomes[key] = value
    return outcomes


def determine_failure_reasons(outcomes: dict[str, str], missing_files: list[str]) -> list[str]:
    reasons: list[str] = []
    for step_name, outcome in outcomes.items():
        if outcome in {"failure", "cancelled", "timed_out"}:
            reasons.append(f"Step '{step_name}' ended with outcome: {outcome}")
    if missing_files:
        reasons.append(
            "Required artifact files are missing: "
            + ", ".join(missing_files)
        )
    if not reasons:
        reasons.append("Job failure detected, but no explicit failing step outcome was provided.")
    return reasons


def collect_latest_log_excerpt(log_dir: Path, max_lines: int) -> str:
    if not log_dir.exists() or not log_dir.is_dir():
        return "No log directory found."

    candidates = sorted(
        log_dir.glob("*.log"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return "No log files found."

    latest = candidates[0]
    try:
        lines = latest.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return f"Failed to read latest log file ({latest.name}): {exc}"

    tail = lines[-max_lines:] if max_lines > 0 else lines
    body = "\n".join(tail).strip()
    if not body:
        body = "(latest log file is empty)"
    return f"File: {latest.as_posix()}\n\n{body}"


def build_diagnostic_markdown(
    commands: list[str],
    reasons: list[str],
    required_files: list[str],
    missing_files: list[str],
    log_excerpt: str,
    generated_at: str,
) -> str:
    required_lines = [
        f"- [{'OK' if path not in missing_files else 'MISSING'}] {path}"
        for path in required_files
    ]

    sections = [
        "# Weekly Workflow Failure Diagnostic",
        "",
        f"- Generated at (UTC): {generated_at}",
        "",
        "## Executed Commands",
        *[f"- {command}" for command in commands],
        "",
        "## Failure Reasons",
        *[f"- {reason}" for reason in reasons],
        "",
        "## Required File Verification",
        *required_lines,
        "",
        "## Latest Log Excerpt",
        "```text",
        log_excerpt,
        "```",
        "",
    ]
    return "\n".join(sections)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a markdown diagnostic artifact for weekly workflow failures."
    )
    parser.add_argument("--root", default=".", help="Repository root path")
    parser.add_argument(
        "--output",
        default="logs/weekly-ops-failure-diagnostic.md",
        help="Output markdown file path relative to root",
    )
    parser.add_argument(
        "--command",
        action="append",
        dest="commands",
        default=None,
        help="Executed command to include in report. Can be repeated.",
    )
    parser.add_argument(
        "--required",
        action="append",
        dest="required_files",
        default=None,
        help="Required file path relative to root. Can be repeated.",
    )
    parser.add_argument(
        "--outcome",
        action="append",
        dest="outcomes",
        default=None,
        help="Step outcome in key=value format. Can be repeated.",
    )
    parser.add_argument(
        "--log-dir",
        default="logs",
        help="Log directory relative to root",
    )
    parser.add_argument(
        "--max-log-lines",
        type=int,
        default=80,
        help="Maximum number of lines to include from latest log",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    root = Path(args.root)
    commands = args.commands or list(DEFAULT_COMMANDS)
    required_files = args.required_files or list(DEFAULT_REQUIRED_FILES)
    outcomes = parse_outcome_pairs(args.outcomes)
    missing = missing_required_files(required_files, root)
    reasons = determine_failure_reasons(outcomes, missing)
    log_excerpt = collect_latest_log_excerpt(root / args.log_dir, args.max_log_lines)

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    content = build_diagnostic_markdown(
        commands=commands,
        reasons=reasons,
        required_files=required_files,
        missing_files=missing,
        log_excerpt=log_excerpt,
        generated_at=generated_at,
    )

    output_path = root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"Wrote weekly failure diagnostic: {output_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
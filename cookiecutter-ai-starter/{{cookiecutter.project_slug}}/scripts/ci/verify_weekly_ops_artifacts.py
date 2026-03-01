from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_REQUIRED_FILES = (
    "docs/ops_reports/latest_ops_report.md",
    "docs/ops_reports/latest_ops_report.html",
    "docs/ops_reports/index.html",
    "logs/ops-report-ci.json",
)


def missing_required_files(required_files: list[str], root: Path) -> list[str]:
    return [path for path in required_files if not (root / path).is_file()]


def build_verification_rows(required_files: list[str], root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for relative_path in required_files:
        status = "OK" if (root / relative_path).is_file() else "MISSING"
        rows.append({"path": relative_path, "status": status})
    return rows


def build_verification_report(required_files: list[str], root: Path) -> dict[str, Any]:
    rows = build_verification_rows(required_files, root)
    missing_count = sum(1 for row in rows if row.get("status") == "MISSING")
    return {
        "root": str(root),
        "checks": rows,
        "summary": {
            "total": len(rows),
            "ok": len(rows) - missing_count,
            "missing": missing_count,
        },
    }


def write_verification_json(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify required files for weekly ops report artifact are present."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root path (default: current directory)",
    )
    parser.add_argument(
        "--required",
        action="append",
        dest="required_files",
        default=None,
        help="Required file path (relative to root). Can be specified multiple times.",
    )
    parser.add_argument(
        "--json-output",
        default="",
        help="Optional output path for machine-readable JSON report (relative to --root when not absolute).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    required_files = args.required_files or list(DEFAULT_REQUIRED_FILES)

    report = build_verification_report(required_files, root)

    output_value = str(args.json_output or "").strip()
    if output_value:
        output_path = Path(output_value)
        if not output_path.is_absolute():
            output_path = root / output_path
        write_verification_json(report, output_path)

    missing = missing_required_files(required_files, root)
    if missing:
        print("Missing required weekly ops artifact files:")
        for path in missing:
            print(f"- {path}")
        return 1

    print("Weekly ops artifact integrity check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
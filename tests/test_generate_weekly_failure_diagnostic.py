from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "ci"
        / "generate_weekly_failure_diagnostic.py"
    )
    spec = importlib.util.spec_from_file_location("generate_weekly_failure_diagnostic", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_required_files_returns_missing_entries(tmp_path):
    module = _load_module()

    existing = module.DEFAULT_REQUIRED_FILES[0]
    existing_path = tmp_path / existing
    existing_path.parent.mkdir(parents=True, exist_ok=True)
    existing_path.write_text("ok", encoding="utf-8")

    missing = module.missing_required_files(list(module.DEFAULT_REQUIRED_FILES), tmp_path)

    assert existing not in missing
    assert set(missing) == set(module.DEFAULT_REQUIRED_FILES[1:])


def test_determine_failure_reasons_includes_step_outcome_and_missing_files():
    module = _load_module()

    reasons = module.determine_failure_reasons(
        outcomes={"generate_weekly_ops_report": "failure", "verify": "success"},
        missing_files=["docs/ops_reports/latest_ops_report.md"],
    )

    assert any("generate_weekly_ops_report" in reason for reason in reasons)
    assert any("Required artifact files are missing" in reason for reason in reasons)


def test_collect_latest_log_excerpt_reads_newest_log_file(tmp_path):
    module = _load_module()

    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    old_file = log_dir / "old.log"
    latest_file = log_dir / "latest.log"
    old_file.write_text("old", encoding="utf-8")
    latest_file.write_text("line1\nline2\nline3", encoding="utf-8")

    old_ts = 1_700_000_000
    new_ts = 1_800_000_000
    old_file.touch()
    latest_file.touch()
    import os

    os.utime(old_file, (old_ts, old_ts))
    os.utime(latest_file, (new_ts, new_ts))

    excerpt = module.collect_latest_log_excerpt(log_dir, max_lines=2)

    assert "latest.log" in excerpt
    assert "line2" in excerpt
    assert "line3" in excerpt
    assert "line1" not in excerpt


def test_build_diagnostic_markdown_contains_all_required_sections():
    module = _load_module()

    report = module.build_diagnostic_markdown(
        commands=["python -m src.main ops-report --days 7 --json > logs/ops-report-ci.json"],
        reasons=["Step 'verify_weekly_artifacts' ended with outcome: failure"],
        required_files=["docs/ops_reports/index.html"],
        missing_files=["docs/ops_reports/index.html"],
        log_excerpt="File: logs/weekly-run.log\n\nERROR sample",
        generated_at="2026-03-01T00:00:00+00:00",
    )

    assert "## Executed Commands" in report
    assert "## Failure Reasons" in report
    assert "## Required File Verification" in report
    assert "## Latest Log Excerpt" in report
    assert "[MISSING] docs/ops_reports/index.html" in report

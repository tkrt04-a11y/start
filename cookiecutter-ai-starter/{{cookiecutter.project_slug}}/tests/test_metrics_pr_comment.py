from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_metrics_pr_comment_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "metrics_pr_comment.py"
    spec = importlib.util.spec_from_file_location("metrics_pr_comment", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_comment_includes_profile_and_resolved_threshold_table():
    module = _load_metrics_pr_comment_module()

    payload = {
        "days": 30,
        "threshold_profile": "stg",
        "thresholds": {
            "daily": {"max_duration_sec": 333.0, "max_failure_rate": 0.12},
            "weekly": {"max_duration_sec": 2400.0, "max_failure_rate": 0.30},
            "monthly": {"max_duration_sec": 4800.0, "max_failure_rate": 0.35},
        },
        "violations": [],
    }

    body = module.build_comment(payload)

    assert body.startswith(module.MARKER)
    assert "- Threshold profile: `stg`" in body
    assert "| Pipeline | Max duration (sec) | Max failure rate |" in body
    assert "| daily | 333 | 0.12 |" in body
    assert "| weekly | 2400 | 0.3 |" in body
    assert "| monthly | 4800 | 0.35 |" in body


def test_build_comment_threshold_table_uses_na_for_missing_values():
    module = _load_metrics_pr_comment_module()

    payload = {
        "days": 14,
        "threshold_profile": "prod",
        "thresholds": {
            "daily": {"max_duration_sec": "invalid", "max_failure_rate": None},
        },
        "violations": [],
    }

    body = module.build_comment(payload)

    assert "| daily | n/a | n/a |" in body
    assert "| weekly | n/a | n/a |" in body
    assert "| monthly | n/a | n/a |" in body


def test_build_comment_includes_previous_comparison_table():
    module = _load_metrics_pr_comment_module()

    current_payload = {
        "days": 30,
        "threshold_profile": "prod",
        "health": {"score": 91},
        "violations": [
            {"pipeline": "daily", "metric": "failure_rate", "threshold": 0.1, "observed": 0.2},
            {"pipeline": "weekly", "metric": "max_duration_sec", "threshold": 1000, "observed": 1500},
            {"pipeline": "weekly", "metric": "failure_rate", "threshold": 0.2, "observed": 0.4},
        ],
    }
    previous_payload = {
        "days": 30,
        "threshold_profile": "prod",
        "health_score": 97,
        "violations": [
            {"pipeline": "daily", "metric": "failure_rate", "threshold": 0.1, "observed": 0.12},
        ],
    }

    body = module.build_comment(current_payload, previous_payload=previous_payload)

    assert "### Comparison with previous result" in body
    assert "| violation_count | 1 | 3 | +2 |" in body
    assert "| health_score | 97 | 91 | -6 |" in body
    assert "| daily.violation_count | 1 | 1 | 0 |" in body
    assert "| weekly.violation_count | 0 | 2 | +2 |" in body
    assert "| monthly.violation_count | 0 | 0 | 0 |" in body


def test_build_comment_gracefully_degrades_without_previous_result():
    module = _load_metrics_pr_comment_module()

    payload = {
        "days": 30,
        "threshold_profile": "prod",
        "violations": [],
    }

    body = module.build_comment(payload, previous_payload=None)

    assert "### Comparison with previous result" in body
    assert "Previous result not found or unreadable; comparison skipped." in body


def test_build_comment_includes_runbook_reference_and_retry_guides_from_ops_report():
    module = _load_metrics_pr_comment_module()

    payload = {
        "days": 30,
        "threshold_profile": "prod",
        "violations": [],
    }
    ops_report_payload = {
        "failed_command_retry_guides": [
            {
                "pipeline": "weekly",
                "suggested_retry_command": "python -m src.main weekly-report --days 7",
                "runbook_reference": "docs/runbook.md#週次パイプライン",
            },
            {
                "pipeline": "daily",
                "suggested_retry_command": "python -m src.main retention",
                "runbook_reference": "docs/runbook.md#日次パイプライン",
            },
        ]
    }

    body = module.build_comment(payload, ops_report_payload=ops_report_payload)

    assert "### Runbook reference and retry guide" in body
    assert "| Pipeline | Suggested retry command | Runbook reference |" in body
    assert "| weekly | python -m src.main weekly-report --days 7 | [docs/runbook.md#週次パイプライン](docs/runbook.md#週次パイプライン) |" in body
    assert "| daily | python -m src.main retention | [docs/runbook.md#日次パイプライン](docs/runbook.md#日次パイプライン) |" in body


def test_build_comment_gracefully_degrades_when_retry_guides_unavailable():
    module = _load_metrics_pr_comment_module()

    payload = {
        "days": 30,
        "threshold_profile": "prod",
        "violations": [],
    }

    body = module.build_comment(payload, ops_report_payload={})

    assert "### Runbook reference and retry guide" in body
    assert "Retry guide unavailable: `failed_command_retry_guides` was not found or was empty in `logs/ops-report-ci.json`." in body


def test_build_comment_includes_continuous_slo_alert_section_and_comparison():
    module = _load_metrics_pr_comment_module()

    payload = {
        "days": 30,
        "threshold_profile": "prod",
        "violations": [],
        "continuous_alert": {
            "severity": "critical",
            "active": True,
            "warning_limit": 3,
            "critical_limit": 5,
            "violated_pipelines": [
                {
                    "pipeline": "weekly",
                    "severity": "critical",
                    "consecutive_failures": 5,
                    "latest_run": "2026-03-01T09:30:00",
                }
            ],
        },
    }
    previous_payload = {
        "days": 30,
        "threshold_profile": "prod",
        "violations": [],
        "continuous_alert": {
            "severity": "warning",
            "active": True,
            "warning_limit": 3,
            "critical_limit": 5,
            "violated_pipelines": [],
        },
    }

    body = module.build_comment(payload, previous_payload=previous_payload)

    assert "### Continuous SLO alert" in body
    assert "- Severity: `critical`" in body
    assert "| Pipeline | Severity | Consecutive failures | Latest run |" in body
    assert "| weekly | critical | 5 | 2026-03-01T09:30:00 |" in body
    assert "| continuous_slo_severity | warning | critical | +1 |" in body

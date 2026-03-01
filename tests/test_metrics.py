from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest

from src.metrics import (
    build_metrics_summary,
    calculate_operational_health_score,
    check_metric_thresholds,
    load_metric_thresholds,
    normalize_health_summary,
    summarize_pipeline_metrics,
)
from src.schema_validation import load_json_schema, validate_json_payload
from src.schema_versions import SCHEMA_VERSION


def _write_metric(logs_dir, name: str, payload: dict) -> None:
    (logs_dir / name).write_text(json.dumps(payload), encoding="utf-8")


def _load_metrics_check_schema() -> dict:
    return load_json_schema(Path("docs/schemas/metrics_check.schema.json"))


def test_summarize_pipeline_metrics_basic(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()

    ts1 = (now - timedelta(days=1)).replace(microsecond=0).isoformat()
    ts2 = now.replace(microsecond=0).isoformat()

    _write_metric(
        logs_dir,
        "daily-metrics-20260301-010101.json",
        {
            "pipeline": "daily",
            "finished_at": ts1,
            "duration_sec": 10,
            "command_failures": 1,
            "alert_count": 2,
            "success": True,
        },
    )
    _write_metric(
        logs_dir,
        "daily-metrics-20260301-020202.json",
        {
            "pipeline": "daily",
            "finished_at": ts2,
            "duration_sec": 20,
            "command_failures": 0,
            "alert_count": 1,
            "success": False,
        },
    )
    _write_metric(
        logs_dir,
        "weekly-metrics-20260301-030303.json",
        {
            "pipeline": "weekly",
            "finished_at": ts2,
            "duration_sec": 30,
            "command_failures": 2,
            "alert_count": 3,
            "success": True,
        },
    )

    summary = summarize_pipeline_metrics(days=30, logs_dir=logs_dir)

    assert summary["total_runs"] == 3
    assert summary["totals"]["command_failures"] == 3
    assert summary["totals"]["alert_count"] == 6

    daily = summary["pipelines"]["daily"]
    assert daily["runs"] == 2
    assert daily["success_rate"] == pytest.approx(0.5)
    assert daily["avg_duration_sec"] == pytest.approx(15.0)
    assert daily["max_duration_sec"] == pytest.approx(20.0)
    assert daily["latest_run"]["timestamp"] == ts2
    assert daily["latest_run"]["success"] is False

    weekly = summary["pipelines"]["weekly"]
    assert weekly["runs"] == 1
    assert weekly["success_rate"] == pytest.approx(1.0)


def test_summarize_pipeline_metrics_days_filter(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()

    recent = (now - timedelta(days=1)).replace(microsecond=0).isoformat()
    old = (now - timedelta(days=40)).replace(microsecond=0).isoformat()

    _write_metric(
        logs_dir,
        "monthly-metrics-20260301-040404.json",
        {
            "pipeline": "monthly",
            "finished_at": recent,
            "duration_sec": 44,
            "command_failures": 1,
            "alert_count": 1,
            "success": True,
        },
    )
    _write_metric(
        logs_dir,
        "monthly-metrics-20260101-040404.json",
        {
            "pipeline": "monthly",
            "finished_at": old,
            "duration_sec": 99,
            "command_failures": 9,
            "alert_count": 9,
            "success": False,
        },
    )

    summary = summarize_pipeline_metrics(days=30, logs_dir=logs_dir)

    assert summary["total_runs"] == 1
    monthly = summary["pipelines"]["monthly"]
    assert monthly["runs"] == 1
    assert summary["totals"]["command_failures"] == 1
    assert summary["totals"]["alert_count"] == 1


def test_load_metric_thresholds_profile_defaults_and_bounds():
    thresholds = load_metric_thresholds(
        {
            "METRIC_THRESHOLD_PROFILE": "stg",
            "METRIC_MAX_DURATION_DAILY_SEC": "invalid",
            "METRIC_MAX_DURATION_WEEKLY_SEC": "0",
            "METRIC_MAX_FAILURE_RATE_DAILY": "1.5",
            "METRIC_MAX_FAILURE_RATE_MONTHLY": "-0.2",
        }
    )

    assert thresholds["daily"]["max_duration_sec"] == pytest.approx(1200.0)
    assert thresholds["weekly"]["max_duration_sec"] == pytest.approx(1.0)
    assert thresholds["daily"]["max_failure_rate"] == pytest.approx(1.0)
    assert thresholds["monthly"]["max_failure_rate"] == pytest.approx(0.0)


def test_load_metric_thresholds_explicit_override_wins_over_profile():
    thresholds = load_metric_thresholds(
        {
            "METRIC_THRESHOLD_PROFILE": "dev",
            "METRIC_MAX_DURATION_DAILY_SEC": "333",
            "METRIC_MAX_FAILURE_RATE_DAILY": "0.12",
        }
    )

    assert thresholds["daily"]["max_duration_sec"] == pytest.approx(333.0)
    assert thresholds["daily"]["max_failure_rate"] == pytest.approx(0.12)
    assert thresholds["weekly"]["max_duration_sec"] == pytest.approx(3600.0)
    assert thresholds["monthly"]["max_failure_rate"] == pytest.approx(0.50)


def test_load_metric_thresholds_unknown_profile_falls_back_to_prod_defaults():
    thresholds = load_metric_thresholds({"METRIC_THRESHOLD_PROFILE": "qa"})

    assert thresholds["daily"]["max_duration_sec"] == pytest.approx(900.0)
    assert thresholds["weekly"]["max_duration_sec"] == pytest.approx(1800.0)
    assert thresholds["monthly"]["max_failure_rate"] == pytest.approx(0.25)


def test_check_metric_thresholds_detects_duration_and_failure_rate(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now().replace(microsecond=0)

    _write_metric(
        logs_dir,
        "daily-metrics-20260301-000001.json",
        {
            "pipeline": "daily",
            "finished_at": now.isoformat(),
            "duration_sec": 12,
            "command_failures": 0,
            "alert_count": 0,
            "success": False,
        },
    )

    result = check_metric_thresholds(
        days=30,
        logs_dir=logs_dir,
        env={
            "METRIC_MAX_DURATION_DAILY_SEC": "10",
            "METRIC_MAX_FAILURE_RATE_DAILY": "0.2",
        },
    )
    violations = result["violations"]

    assert len(violations) == 2
    assert {item["metric"] for item in violations} == {"max_duration_sec", "failure_rate"}
    assert all(item["pipeline"] == "daily" for item in violations)


def test_check_metric_thresholds_includes_resolved_profile(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    result = check_metric_thresholds(
        days=30,
        logs_dir=logs_dir,
        env={"METRIC_THRESHOLD_PROFILE": "unknown"},
    )

    assert result["threshold_profile"] == "prod"


def test_calculate_operational_health_score_boundary_best_case():
    summary = {
        "pipelines": {
            "daily": {"runs": 2, "success_rate": 1.0},
            "weekly": {"runs": 1, "success_rate": 1.0},
            "monthly": {"runs": 1, "success_rate": 1.0},
        },
        "totals": {"command_failures": 0, "alert_count": 0},
    }

    health = calculate_operational_health_score(summary=summary, violations=[])

    assert health["score"] == 100
    assert health["factors"]["violation_count"] == 0
    assert health["factors"]["command_failures"] == 0
    assert health["factors"]["alert_count"] == 0


def test_calculate_operational_health_score_boundary_worst_case_clamped_to_zero():
    summary = {
        "pipelines": {
            "daily": {"runs": 3, "success_rate": 0.0},
            "weekly": {"runs": 2, "success_rate": 0.0},
        },
        "totals": {"command_failures": 99, "alert_count": 999},
    }
    violations = [{"pipeline": "daily", "metric": "failure_rate"}] * 20

    health = calculate_operational_health_score(summary=summary, violations=violations)

    assert health["score"] == 0
    assert health["factors"]["violation_count"] == 20


def test_calculate_operational_health_score_decreases_when_failures_or_violations_increase():
    base_summary = {
        "pipelines": {
            "daily": {"runs": 2, "success_rate": 1.0},
            "weekly": {"runs": 1, "success_rate": 1.0},
        },
        "totals": {"command_failures": 0, "alert_count": 0},
    }

    base = calculate_operational_health_score(summary=base_summary, violations=[])
    worse_by_violations = calculate_operational_health_score(
        summary=base_summary,
        violations=[{"pipeline": "daily", "metric": "max_duration_sec"}] * 3,
    )
    worse_by_failures = calculate_operational_health_score(
        summary={
            "pipelines": base_summary["pipelines"],
            "totals": {"command_failures": 2, "alert_count": 5},
        },
        violations=[],
    )

    assert worse_by_violations["score"] < base["score"]
    assert worse_by_failures["score"] < base["score"]


def test_build_metrics_summary_includes_health_score_and_breakdown(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now().replace(microsecond=0)

    _write_metric(
        logs_dir,
        "daily-metrics-20260301-000001.json",
        {
            "pipeline": "daily",
            "finished_at": now.isoformat(),
            "duration_sec": 12,
            "command_failures": 1,
            "alert_count": 2,
            "success": False,
        },
    )

    payload = build_metrics_summary(days=30, logs_dir=logs_dir)
    result = check_metric_thresholds(days=30, logs_dir=logs_dir)
    expected = normalize_health_summary(result.get("health"))

    assert payload["health_score"] == expected["health_score"]
    assert payload["health_breakdown"] == expected["health_breakdown"]


def test_metrics_check_json_payload_conforms_schema(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now().replace(microsecond=0)

    _write_metric(
        logs_dir,
        "daily-metrics-20260301-000001.json",
        {
            "pipeline": "daily",
            "finished_at": now.isoformat(),
            "duration_sec": 12,
            "command_failures": 0,
            "alert_count": 0,
            "success": False,
        },
    )

    result = check_metric_thresholds(
        days=30,
        logs_dir=logs_dir,
        env={
            "METRIC_MAX_DURATION_DAILY_SEC": "10",
            "METRIC_MAX_FAILURE_RATE_DAILY": "0.2",
        },
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "days": 30,
        "threshold_profile": result["threshold_profile"],
        "violations": result["violations"],
    }

    validate_json_payload(payload, _load_metrics_check_schema(), schema_name="metrics_check.schema.json")

"""Metrics aggregation helpers for pipeline run artifacts."""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from typing import Any, Mapping


_ALLOWED_PIPELINES = {"daily", "weekly", "monthly"}

_DEFAULT_DURATION_THRESHOLDS_SEC = {
    "daily": 900.0,
    "weekly": 1800.0,
    "monthly": 3600.0,
}

_DEFAULT_FAILURE_RATE_THRESHOLDS = {
    "daily": 0.10,
    "weekly": 0.20,
    "monthly": 0.25,
}

_DEFAULT_THRESHOLD_PROFILES = {
    "dev": {
        "duration_sec": {
            "daily": 1800.0,
            "weekly": 3600.0,
            "monthly": 7200.0,
        },
        "failure_rate": {
            "daily": 0.30,
            "weekly": 0.40,
            "monthly": 0.50,
        },
    },
    "stg": {
        "duration_sec": {
            "daily": 1200.0,
            "weekly": 2400.0,
            "monthly": 4800.0,
        },
        "failure_rate": {
            "daily": 0.20,
            "weekly": 0.30,
            "monthly": 0.35,
        },
    },
    "prod": {
        "duration_sec": _DEFAULT_DURATION_THRESHOLDS_SEC,
        "failure_rate": _DEFAULT_FAILURE_RATE_THRESHOLDS,
    },
}

_DEFAULT_THRESHOLD_PROFILE = "prod"
_THRESHOLD_PROFILE_ENV_KEY = "METRIC_THRESHOLD_PROFILE"
_SLO_CONSECUTIVE_ALERT_ENV_KEY = "METRIC_SLO_CONSECUTIVE_ALERT_N"
_SLO_CONSECUTIVE_ALERT_DEFAULT = 3
_SLO_CONSECUTIVE_ALERT_CRITICAL_ENV_KEY = "METRIC_SLO_CONSECUTIVE_ALERT_CRITICAL_N"
_SLO_CONSECUTIVE_ALERT_CRITICAL_DEFAULT = 5

_DURATION_ENV_KEYS = {
    "daily": "METRIC_MAX_DURATION_DAILY_SEC",
    "weekly": "METRIC_MAX_DURATION_WEEKLY_SEC",
    "monthly": "METRIC_MAX_DURATION_MONTHLY_SEC",
}

_FAILURE_RATE_ENV_KEYS = {
    "daily": "METRIC_MAX_FAILURE_RATE_DAILY",
    "weekly": "METRIC_MAX_FAILURE_RATE_WEEKLY",
    "monthly": "METRIC_MAX_FAILURE_RATE_MONTHLY",
}


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.replace(tzinfo=None)
    return parsed


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _read_positive_int_env(
    env: Mapping[str, str],
    key: str,
    default: int,
    *,
    minimum: int = 1,
) -> int:
    raw = str(env.get(key, "")).strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _read_float_threshold(
    env: Mapping[str, str],
    key: str,
    default: float,
    *,
    minimum: float,
    maximum: float | None = None,
) -> float:
    raw = str(env.get(key, "")).strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value < minimum:
        return minimum
    if maximum is not None and value > maximum:
        return maximum
    return value


def resolve_metric_threshold_profile(env: Mapping[str, str] | None = None) -> str:
    """Resolve active threshold profile from env with safe fallback."""
    source_env = os.environ if env is None else env
    raw_profile = str(source_env.get(_THRESHOLD_PROFILE_ENV_KEY, "")).strip().lower()
    if raw_profile in _DEFAULT_THRESHOLD_PROFILES:
        return raw_profile
    return _DEFAULT_THRESHOLD_PROFILE


def load_metric_thresholds(env: Mapping[str, str] | None = None) -> dict[str, dict[str, float]]:
    """Load metric thresholds from env with per-pipeline defaults."""
    source_env = os.environ if env is None else env
    profile = resolve_metric_threshold_profile(source_env)
    profile_defaults = _DEFAULT_THRESHOLD_PROFILES[profile]
    thresholds: dict[str, dict[str, float]] = {}
    for pipeline in sorted(_ALLOWED_PIPELINES):
        duration_default = float(profile_defaults["duration_sec"][pipeline])
        failure_default = float(profile_defaults["failure_rate"][pipeline])
        thresholds[pipeline] = {
            "max_duration_sec": _read_float_threshold(
                source_env,
                _DURATION_ENV_KEYS[pipeline],
                duration_default,
                minimum=1.0,
            ),
            "max_failure_rate": _read_float_threshold(
                source_env,
                _FAILURE_RATE_ENV_KEYS[pipeline],
                failure_default,
                minimum=0.0,
                maximum=1.0,
            ),
        }
    return thresholds


def evaluate_metric_thresholds(
    summary: Mapping[str, Any],
    thresholds: Mapping[str, Mapping[str, float]],
) -> list[dict[str, Any]]:
    """Evaluate metric threshold violations against a metrics summary."""
    violations: list[dict[str, Any]] = []
    pipelines = summary.get("pipelines", {})
    if not isinstance(pipelines, dict):
        return violations

    for pipeline, values in pipelines.items():
        if pipeline not in _ALLOWED_PIPELINES:
            continue
        if not isinstance(values, dict):
            continue

        runs = _to_int(values.get("runs"))
        if runs <= 0:
            continue

        threshold_set = thresholds.get(pipeline, {})
        duration_threshold = _to_float(threshold_set.get("max_duration_sec"))
        failure_rate_threshold = _to_float(threshold_set.get("max_failure_rate"))

        observed_max_duration = _to_float(values.get("max_duration_sec"))
        if observed_max_duration > duration_threshold:
            violations.append(
                {
                    "pipeline": pipeline,
                    "metric": "max_duration_sec",
                    "threshold": duration_threshold,
                    "observed": observed_max_duration,
                }
            )

        success_rate = _to_float(values.get("success_rate"))
        observed_failure_rate = max(0.0, min(1.0, 1.0 - success_rate))
        if observed_failure_rate > failure_rate_threshold:
            violations.append(
                {
                    "pipeline": pipeline,
                    "metric": "failure_rate",
                    "threshold": failure_rate_threshold,
                    "observed": observed_failure_rate,
                }
            )

    return violations


def evaluate_consecutive_slo_alert(
    days: int = 30,
    logs_dir: str | Path = "logs",
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Evaluate consecutive run failures and return alert signal.

    A run with ``success=False`` is treated as one SLO violation event.
    If a pipeline has consecutive failures greater than or equal to configured
    threshold, the pipeline is marked for continuous alert.
    """
    source_env = os.environ if env is None else env
    consecutive_limit = _read_positive_int_env(
        source_env,
        _SLO_CONSECUTIVE_ALERT_ENV_KEY,
        _SLO_CONSECUTIVE_ALERT_DEFAULT,
        minimum=1,
    )
    critical_limit = _read_positive_int_env(
        source_env,
        _SLO_CONSECUTIVE_ALERT_CRITICAL_ENV_KEY,
        _SLO_CONSECUTIVE_ALERT_CRITICAL_DEFAULT,
        minimum=consecutive_limit,
    )

    now = datetime.now()
    window_start = None if days <= 0 else (now - timedelta(days=days))
    per_pipeline_runs: dict[str, list[tuple[datetime, bool, str]]] = {}

    log_path = Path(logs_dir)
    for file_path in sorted(log_path.glob("*-metrics-*.json")):
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(payload, dict):
            continue
        pipeline = str(payload.get("pipeline", "")).strip().lower()
        if pipeline not in _ALLOWED_PIPELINES:
            continue

        timestamp_text = str(payload.get("finished_at") or payload.get("started_at") or "").strip()
        timestamp = _parse_timestamp(timestamp_text)
        if timestamp is None:
            continue
        if window_start is not None and timestamp < window_start:
            continue

        success = bool(payload.get("success", False))
        runs = per_pipeline_runs.setdefault(pipeline, [])
        runs.append((timestamp, success, timestamp_text))

    violated_pipelines: list[dict[str, Any]] = []
    severity_rank = {"none": 0, "warning": 1, "critical": 2}
    overall_severity = "none"
    for pipeline in sorted(per_pipeline_runs.keys()):
        runs = sorted(per_pipeline_runs[pipeline], key=lambda item: item[0], reverse=True)
        consecutive_failures = 0
        latest_timestamp = ""
        for index, (_, success, timestamp_text) in enumerate(runs):
            if index == 0:
                latest_timestamp = timestamp_text
            if success:
                break
            consecutive_failures += 1

        if consecutive_failures >= consecutive_limit:
            pipeline_severity = "critical" if consecutive_failures >= critical_limit else "warning"
            if severity_rank[pipeline_severity] > severity_rank[overall_severity]:
                overall_severity = pipeline_severity
            violated_pipelines.append(
                {
                    "pipeline": pipeline,
                    "consecutive_failures": consecutive_failures,
                    "latest_run": latest_timestamp,
                    "severity": pipeline_severity,
                }
            )

    return {
        "limit": consecutive_limit,
        "warning_limit": consecutive_limit,
        "critical_limit": critical_limit,
        "severity": overall_severity,
        "active": overall_severity != "none",
        "violated_pipelines": violated_pipelines,
    }


def check_metric_thresholds(
    days: int = 30,
    logs_dir: str | Path = "logs",
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Summarize metrics and return threshold evaluation result."""
    summary = summarize_pipeline_metrics(days=days, logs_dir=logs_dir)
    profile = resolve_metric_threshold_profile(env=env)
    thresholds = load_metric_thresholds(env=env)
    violations = evaluate_metric_thresholds(summary, thresholds)
    continuous_alert = evaluate_consecutive_slo_alert(days=days, logs_dir=logs_dir, env=env)
    health = calculate_operational_health_score(summary=summary, violations=violations)
    return {
        "days": days,
        "threshold_profile": profile,
        "thresholds": thresholds,
        "violations": violations,
        "continuous_alert": continuous_alert,
        "health": health,
        "summary": summary,
    }


def summarize_pipeline_metrics(days: int = 30, logs_dir: str | Path = "logs") -> dict[str, Any]:
    """Load ``logs/*-metrics-*.json`` and aggregate summary metrics."""
    now = datetime.now()
    window_start = None if days <= 0 else (now - timedelta(days=days))

    per_pipeline: dict[str, dict[str, Any]] = {}
    total_command_failures = 0
    total_alert_count = 0
    included_runs = 0

    log_path = Path(logs_dir)
    for file_path in sorted(log_path.glob("*-metrics-*.json")):
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(payload, dict):
            continue
        pipeline = str(payload.get("pipeline", "")).strip().lower()
        if pipeline not in _ALLOWED_PIPELINES:
            continue

        timestamp_text = str(payload.get("finished_at") or payload.get("started_at") or "").strip()
        timestamp = _parse_timestamp(timestamp_text)
        if timestamp is None:
            continue
        if window_start is not None and timestamp < window_start:
            continue

        stats = per_pipeline.setdefault(
            pipeline,
            {
                "runs": 0,
                "success_count": 0,
                "duration_total": 0.0,
                "max_duration_sec": 0.0,
                "latest_run": {"timestamp": "", "success": False},
                "latest_dt": datetime.min,
            },
        )

        included_runs += 1
        stats["runs"] += 1

        success = bool(payload.get("success", False))
        if success:
            stats["success_count"] += 1

        duration_sec = _to_float(payload.get("duration_sec"))
        stats["duration_total"] += duration_sec
        if duration_sec > stats["max_duration_sec"]:
            stats["max_duration_sec"] = duration_sec

        command_failures = _to_int(payload.get("command_failures"))
        alert_count = _to_int(payload.get("alert_count"))
        total_command_failures += command_failures
        total_alert_count += alert_count

        if timestamp >= stats["latest_dt"]:
            stats["latest_dt"] = timestamp
            stats["latest_run"] = {"timestamp": timestamp_text, "success": success}

    pipelines: dict[str, dict[str, Any]] = {}
    for pipeline in sorted(per_pipeline.keys()):
        stats = per_pipeline[pipeline]
        runs = int(stats["runs"])
        success_count = int(stats["success_count"])
        avg_duration = (stats["duration_total"] / runs) if runs else 0.0
        pipelines[pipeline] = {
            "runs": runs,
            "success_rate": (success_count / runs) if runs else 0.0,
            "avg_duration_sec": avg_duration,
            "max_duration_sec": float(stats["max_duration_sec"]),
            "latest_run": stats["latest_run"],
        }

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "days": days,
        "window_start": window_start.isoformat(timespec="seconds") if window_start else None,
        "total_runs": included_runs,
        "pipelines": pipelines,
        "totals": {
            "command_failures": total_command_failures,
            "alert_count": total_alert_count,
        },
    }


def calculate_operational_health_score(
    summary: Mapping[str, Any],
    violations: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Calculate a single operational health score (0-100) from recent metrics.

    Formula (simple weighted penalties):
    - Base score starts at 100.
    - Pipeline success rate penalty: ``(1 - avg_pipeline_success_rate) * 60``
    - Threshold violation penalty: ``min(25, violation_count * 5)``
    - Command failure penalty: ``min(10, command_failures * 2)``
    - Alert volume penalty (lightweight): ``min(5, alert_count * 0.2)``
    - Final score is clamped to ``0..100`` and rounded to integer.
    """
    pipelines = summary.get("pipelines", {}) if isinstance(summary.get("pipelines"), dict) else {}
    active_success_rates: list[float] = []
    for item in pipelines.values():
        if not isinstance(item, Mapping):
            continue
        runs = _to_int(item.get("runs"))
        if runs <= 0:
            continue
        success_rate = max(0.0, min(1.0, _to_float(item.get("success_rate"))))
        active_success_rates.append(success_rate)

    average_success_rate = (
        sum(active_success_rates) / len(active_success_rates) if active_success_rates else 0.0
    )

    totals = summary.get("totals", {}) if isinstance(summary.get("totals"), dict) else {}
    command_failures = max(0, _to_int(totals.get("command_failures")))
    alert_count = max(0, _to_int(totals.get("alert_count")))
    violation_count = sum(1 for item in (violations or []) if isinstance(item, Mapping))

    success_penalty = (1.0 - average_success_rate) * 60.0
    violation_penalty = min(25.0, float(violation_count) * 5.0)
    command_failure_penalty = min(10.0, float(command_failures) * 2.0)
    alert_penalty = min(5.0, float(alert_count) * 0.2)

    raw_score = 100.0 - (success_penalty + violation_penalty + command_failure_penalty + alert_penalty)
    score = max(0, min(100, int(round(raw_score))))

    return {
        "score": score,
        "factors": {
            "average_pipeline_success_rate": average_success_rate,
            "violation_count": violation_count,
            "command_failures": command_failures,
            "alert_count": alert_count,
        },
        "penalties": {
            "success_rate": success_penalty,
            "violations": violation_penalty,
            "command_failures": command_failure_penalty,
            "alerts": alert_penalty,
        },
        "formula": (
            "score = clamp(100 - ((1 - avg_success_rate) * 60 + min(25, violations * 5) "
            "+ min(10, command_failures * 2) + min(5, alert_count * 0.2)), 0, 100)"
        ),
    }


def normalize_health_summary(health: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = health if isinstance(health, Mapping) else {}
    return {
        "health_score": _to_int(payload.get("score")),
        "health_breakdown": {
            "factors": dict(payload.get("factors", {})) if isinstance(payload.get("factors"), Mapping) else {},
            "penalties": (
                dict(payload.get("penalties", {})) if isinstance(payload.get("penalties"), Mapping) else {}
            ),
            "formula": str(payload.get("formula", "")),
        },
    }


def build_metrics_summary(
    days: int = 30,
    logs_dir: str | Path = "logs",
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build metrics-summary payload with unified health fields."""
    result = check_metric_thresholds(days=days, logs_dir=logs_dir, env=env)
    summary = result.get("summary", {}) if isinstance(result.get("summary"), dict) else {}
    payload = dict(summary)
    payload.update(normalize_health_summary(result.get("health") if isinstance(result.get("health"), Mapping) else None))
    return payload


def format_metrics_summary_text(summary: dict[str, Any]) -> str:
    """Render aggregated metrics as human readable text."""
    days = summary.get("days", 30)
    window_start = summary.get("window_start")
    lines = [f"Pipeline metrics summary (last {days} days)"]
    if window_start:
        lines.append(f"Window start: {window_start}")
    lines.append(f"Total runs: {summary.get('total_runs', 0)}")

    pipelines = summary.get("pipelines", {})
    if not pipelines:
        lines.append("No metrics files found in window.")
    else:
        lines.append("")
        for pipeline in sorted(pipelines.keys()):
            item = pipelines[pipeline]
            runs = int(item.get("runs", 0))
            success_rate = float(item.get("success_rate", 0.0)) * 100
            avg_duration = float(item.get("avg_duration_sec", 0.0))
            max_duration = float(item.get("max_duration_sec", 0.0))
            latest_run = item.get("latest_run", {}) if isinstance(item.get("latest_run"), dict) else {}
            latest_timestamp = latest_run.get("timestamp", "")
            latest_success = bool(latest_run.get("success", False))
            lines.append(f"- {pipeline}: runs={runs}, success_rate={success_rate:.1f}%")
            lines.append(f"  duration_sec(avg/max): {avg_duration:.2f}/{max_duration:.2f}")
            lines.append(f"  latest: {latest_timestamp} success={latest_success}")

    totals = summary.get("totals", {}) if isinstance(summary.get("totals"), dict) else {}
    lines.append("")
    lines.append(f"Total command_failures: {int(totals.get('command_failures', 0))}")
    lines.append(f"Total alert_count: {int(totals.get('alert_count', 0))}")

    health_score = _to_int(summary.get("health_score"))
    health_breakdown = summary.get("health_breakdown", {})
    factors = health_breakdown.get("factors", {}) if isinstance(health_breakdown, dict) else {}
    penalties = health_breakdown.get("penalties", {}) if isinstance(health_breakdown, dict) else {}
    formula = health_breakdown.get("formula", "") if isinstance(health_breakdown, dict) else ""

    lines.append("")
    lines.append(f"health_score: {health_score}")
    lines.append("health_breakdown:")
    lines.append(
        "  factors: "
        f"avg_success_rate={_to_float(factors.get('average_pipeline_success_rate')):.4f}, "
        f"violation_count={_to_int(factors.get('violation_count'))}, "
        f"command_failures={_to_int(factors.get('command_failures'))}, "
        f"alert_count={_to_int(factors.get('alert_count'))}"
    )
    lines.append(
        "  penalties: "
        f"success_rate={_to_float(penalties.get('success_rate')):.4f}, "
        f"violations={_to_float(penalties.get('violations')):.4f}, "
        f"command_failures={_to_float(penalties.get('command_failures')):.4f}, "
        f"alerts={_to_float(penalties.get('alerts')):.4f}"
    )
    lines.append(f"  formula: {formula}")
    return "\n".join(lines)

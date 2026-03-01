"""Environment and configuration diagnostics for CLI."""

from __future__ import annotations

import json
import os


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _fail_on_warnings_enabled() -> bool:
    return _is_truthy(os.getenv("DOCTOR_FAIL_ON_WARNINGS", ""))


def run_doctor() -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    infos: list[str] = []

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_key:
        infos.append("OPENAI_API_KEY is set")
    else:
        warnings.append("OPENAI_API_KEY is not set (AI features will use fallback)")

    promoted_min = os.getenv("PROMOTED_MIN_COUNT", "1").strip()
    if promoted_min:
        try:
            if int(promoted_min) < 0:
                errors.append("PROMOTED_MIN_COUNT must be >= 0")
        except ValueError:
            errors.append("PROMOTED_MIN_COUNT must be an integer")

    alerts_max_lines = os.getenv("ALERTS_MAX_LINES", "500").strip()
    if alerts_max_lines:
        try:
            if int(alerts_max_lines) < 50:
                warnings.append("ALERTS_MAX_LINES is very small (< 50)")
        except ValueError:
            errors.append("ALERTS_MAX_LINES must be an integer")

    retries = os.getenv("CONNECTOR_RETRIES", "3").strip()
    if retries:
        try:
            if int(retries) < 1:
                errors.append("CONNECTOR_RETRIES must be >= 1")
        except ValueError:
            errors.append("CONNECTOR_RETRIES must be an integer")

    backoff = os.getenv("CONNECTOR_BACKOFF_SEC", "0.5").strip()
    if backoff:
        try:
            if float(backoff) < 0:
                errors.append("CONNECTOR_BACKOFF_SEC must be >= 0")
        except ValueError:
            errors.append("CONNECTOR_BACKOFF_SEC must be a number")

    webhook_url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    if webhook_url and not (webhook_url.startswith("http://") or webhook_url.startswith("https://")):
        errors.append("ALERT_WEBHOOK_URL must start with http:// or https://")

    issue_sync_enabled = os.getenv("AUTO_SYNC_PROMOTED_ISSUES", "").strip().lower() in {"1", "true", "yes", "on"}
    if issue_sync_enabled:
        repo = os.getenv("GITHUB_REPO", "").strip()
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if not repo:
            errors.append("GITHUB_REPO is required when AUTO_SYNC_PROMOTED_ISSUES is enabled")
        if not token:
            errors.append("GITHUB_TOKEN is required when AUTO_SYNC_PROMOTED_ISSUES is enabled")

    return {"errors": errors, "warnings": warnings, "infos": infos}


def print_doctor_report() -> None:
    result = run_doctor()
    errors = result["errors"]
    warnings = result["warnings"]
    infos = result["infos"]
    fail_on_warnings = _fail_on_warnings_enabled()

    print("Doctor report")
    print(f"- errors: {len(errors)}")
    print(f"- warnings: {len(warnings)}")
    print(f"- fail_on_warnings: {'on' if fail_on_warnings else 'off'}")

    for item in infos:
        print(f"INFO: {item}")
    for item in warnings:
        print(f"WARN: {item}")
    for item in errors:
        print(f"ERROR: {item}")

    ok = len(errors) == 0 and (len(warnings) == 0 if fail_on_warnings else True)
    if ok:
        print("Doctor check passed.")


def print_doctor_report_json() -> None:
    result = run_doctor()
    fail_on_warnings = _fail_on_warnings_enabled()
    ok = len(result["errors"]) == 0 and (len(result["warnings"]) == 0 if fail_on_warnings else True)
    payload = {
        "ok": ok,
        "fail_on_warnings": fail_on_warnings,
        "errors": result["errors"],
        "warnings": result["warnings"],
        "infos": result["infos"],
    }
    print(json.dumps(payload, ensure_ascii=False))

"""Utilities to sync promoted actions into GitHub issues."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from typing import Any

import requests


TITLE_PREFIX = "[AI-STARTER] "
META_PREFIX = "ai-starter-meta"
PERIOD_LABEL_PREFIX = "ai-starter"
ASSIGNEE_RULE_DEFAULT_KEY = "default"
ISSUE_SYNC_MAX_RETRIES = 3
ISSUE_SYNC_INITIAL_BACKOFF_SEC = 1.0
ISSUE_SYNC_TIMEOUT_SEC = 20
ISSUE_SYNC_RETRIES_ENV = "ISSUE_SYNC_RETRIES"
ISSUE_SYNC_BACKOFF_SEC_ENV = "ISSUE_SYNC_BACKOFF_SEC"
META_PATTERN = re.compile(
    r"<!--\s*ai-starter-meta:\s*action_hash=([0-9a-f]+);\s*period_key=([^;<>]*)\s*-->",
    re.IGNORECASE,
)
logger = logging.getLogger(__name__)


def _read_int_env_with_fallback(env_name: str, default: int, min_value: int = 0) -> int:
    raw_value = os.getenv(env_name)
    if raw_value is None or not str(raw_value).strip():
        return default
    is_valid = True
    try:
        parsed = int(str(raw_value).strip())
    except (TypeError, ValueError):
        parsed = default
        is_valid = False
    if parsed < min_value:
        parsed = default
        is_valid = False
    if not is_valid:
        logger.warning(
            "Invalid issue sync env value; using default (env=%s, raw=%r, default=%s)",
            env_name,
            raw_value,
            default,
        )
    return parsed


def _read_float_env_with_fallback(env_name: str, default: float, min_exclusive: float = 0.0) -> float:
    raw_value = os.getenv(env_name)
    if raw_value is None or not str(raw_value).strip():
        return default
    is_valid = True
    try:
        parsed = float(str(raw_value).strip())
    except (TypeError, ValueError):
        parsed = default
        is_valid = False
    if parsed <= min_exclusive:
        parsed = default
        is_valid = False
    if not is_valid:
        logger.warning(
            "Invalid issue sync env value; using default (env=%s, raw=%r, default=%.2f)",
            env_name,
            raw_value,
            default,
        )
    return parsed


def _resolve_issue_sync_retry_config() -> tuple[int, float]:
    max_retries = _read_int_env_with_fallback(
        ISSUE_SYNC_RETRIES_ENV,
        ISSUE_SYNC_MAX_RETRIES,
        min_value=0,
    )
    initial_backoff_sec = _read_float_env_with_fallback(
        ISSUE_SYNC_BACKOFF_SEC_ENV,
        ISSUE_SYNC_INITIAL_BACKOFF_SEC,
        min_exclusive=0.0,
    )
    return max_retries, initial_backoff_sec


def _extract_response_message(response: Any) -> str:
    try:
        payload = response.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    text = getattr(response, "text", "")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return "(no response message)"


def _is_secondary_rate_limited(response: Any) -> bool:
    status_code = int(getattr(response, "status_code", 0) or 0)
    if status_code != 403:
        return False
    message = _extract_response_message(response).lower()
    return "secondary rate limit" in message


def _compute_retry_wait_seconds(
    response: Any,
    attempt: int,
    now_epoch: float | None = None,
    initial_backoff_sec: float = ISSUE_SYNC_INITIAL_BACKOFF_SEC,
) -> float:
    headers = getattr(response, "headers", {}) or {}

    retry_after_value = headers.get("Retry-After")
    if retry_after_value is not None:
        try:
            retry_after_sec = float(str(retry_after_value).strip())
            if retry_after_sec > 0:
                return retry_after_sec
        except (TypeError, ValueError):
            pass

    reset_value = headers.get("X-RateLimit-Reset")
    if reset_value is not None:
        try:
            now = time.time() if now_epoch is None else now_epoch
            reset_epoch = float(str(reset_value).strip())
            wait_sec = (reset_epoch - now) + 1.0
            if wait_sec > 0:
                return wait_sec
        except (TypeError, ValueError):
            pass

    return initial_backoff_sec * (2**attempt)


def _request_with_rate_limit_retry(
    request_func: Any,
    method: str,
    url: str,
    *,
    max_retries: int | None = None,
    initial_backoff_sec: float | None = None,
    **kwargs: Any,
) -> Any:
    resolved_max_retries = max_retries
    resolved_initial_backoff_sec = initial_backoff_sec
    if resolved_max_retries is None or resolved_initial_backoff_sec is None:
        configured_retries, configured_backoff = _resolve_issue_sync_retry_config()
        if resolved_max_retries is None:
            resolved_max_retries = configured_retries
        if resolved_initial_backoff_sec is None:
            resolved_initial_backoff_sec = configured_backoff

    for attempt in range(resolved_max_retries + 1):
        response = request_func(url, **kwargs)
        status_code = int(getattr(response, "status_code", 200) or 200)
        is_rate_limited = status_code == 429 or _is_secondary_rate_limited(response)
        if not is_rate_limited:
            response.raise_for_status()
            return response

        wait_sec = _compute_retry_wait_seconds(
            response,
            attempt,
            initial_backoff_sec=resolved_initial_backoff_sec,
        )
        message = _extract_response_message(response)
        if attempt >= resolved_max_retries:
            raise RuntimeError(
                "GitHub issue sync request failed after retries "
                f"(method={method}, url={url}, status={status_code}, "
                f"attempt={attempt + 1}/{resolved_max_retries + 1}, message={message})"
            )

        logger.warning(
            "GitHub issue sync rate-limited; retrying "
            "(method=%s, url=%s, status=%s, attempt=%s/%s, wait_sec=%.2f, message=%s)",
            method,
            url,
            status_code,
            attempt + 1,
            resolved_max_retries + 1,
            wait_sec,
            message,
        )
        time.sleep(wait_sec)

    raise RuntimeError(f"Unexpected retry loop exit for GitHub issue sync request: {method} {url}")


def _issue_title_from_action(action: str) -> str:
    return f"{TITLE_PREFIX}{action.strip()}"


def _action_hash(action: str) -> str:
    return hashlib.sha256(action.strip().encode("utf-8")).hexdigest()


def _build_meta_marker(action_hash: str, period_key: str) -> str:
    return f"<!-- {META_PREFIX}: action_hash={action_hash}; period_key={period_key} -->"


def _normalize_source_period_type(source_period_type: str | None) -> str:
    normalized = (source_period_type or "").strip().lower()
    if normalized in {"weekly", "monthly"}:
        return normalized
    return ""


def _build_issue_body(action: str, period_key: str, source_period_type: str, marker: str) -> str:
    period_type_text = source_period_type or "unspecified"
    period_key_text = period_key or "N/A"
    return (
        "## Source Period\n"
        f"- Type: {period_type_text}\n"
        f"- Key: {period_key_text}\n\n"
        "## Action\n"
        f"- {action.strip()}\n\n"
        "## Context\n"
        "- This issue was auto-generated from promoted actions sync.\n\n"
        "## Metadata\n"
        f"{marker}\n"
    )


def _build_issue_labels(
    labels: list[str] | None,
    source_period_type: str,
    include_period_label: bool,
) -> list[str]:
    issue_labels = list(labels) if labels else []
    if include_period_label and source_period_type:
        period_label = f"{PERIOD_LABEL_PREFIX}-{source_period_type}"
        if period_label not in issue_labels:
            issue_labels.append(period_label)
    return issue_labels


def _extract_meta_marker(body: str) -> tuple[str, str] | None:
    match = META_PATTERN.search(body)
    if not match:
        return None
    return (match.group(1).lower(), match.group(2).strip())


def parse_issue_assignee_rules(raw_rules: str | None) -> dict[str, list[str]]:
    parsed_rules: dict[str, list[str]] = {}
    for rule in (raw_rules or "").split(";"):
        normalized_rule = rule.strip()
        if not normalized_rule:
            continue
        if ":" not in normalized_rule:
            raise ValueError(f"Invalid rule '{normalized_rule}': expected 'label:assignee1,assignee2'")
        rule_key_text, assignee_text = normalized_rule.split(":", 1)
        rule_key = rule_key_text.strip().lower()
        if not rule_key:
            raise ValueError(f"Invalid rule '{normalized_rule}': label must not be empty")
        assignees = [item.strip() for item in assignee_text.split(",") if item.strip()]
        if not assignees:
            raise ValueError(f"Invalid rule '{normalized_rule}': assignee list must not be empty")
        parsed_rules[rule_key] = assignees
    return parsed_rules


def resolve_issue_assignees(
    explicit_assignees: list[str] | None,
    labels: list[str] | None,
    source_period_type: str | None,
    include_period_label: bool,
    assignee_rules: dict[str, list[str]] | None,
) -> list[str] | None:
    if explicit_assignees:
        return explicit_assignees
    if not assignee_rules:
        return None

    normalized_source_period_type = _normalize_source_period_type(source_period_type)
    issue_labels = _build_issue_labels(labels, normalized_source_period_type, include_period_label)
    for label in issue_labels:
        matched_assignees = assignee_rules.get(label.strip().lower())
        if matched_assignees:
            return list(matched_assignees)

    default_assignees = assignee_rules.get(ASSIGNEE_RULE_DEFAULT_KEY)
    if default_assignees:
        return list(default_assignees)
    return None


def sync_promoted_actions_to_github_issues(
    promoted_actions: list[str],
    repo: str,
    token: str,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
    period_key: str | None = None,
    source_period_type: str | None = None,
    include_period_label: bool = False,
) -> dict[str, int]:
    """Create GitHub issues for promoted actions if they do not already exist."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    normalized_period_key = (period_key or "").strip()
    normalized_source_period_type = _normalize_source_period_type(source_period_type)
    existing_titles, existing_meta_keys = _fetch_open_issue_index(repo, headers)

    created = 0
    skipped_existing = 0

    for action in promoted_actions:
        title = _issue_title_from_action(action)
        meta_key = (_action_hash(action), normalized_period_key)
        if title in existing_titles or meta_key in existing_meta_keys:
            skipped_existing += 1
            continue

        marker = _build_meta_marker(meta_key[0], meta_key[1])
        body = _build_issue_body(action, normalized_period_key, normalized_source_period_type, marker)
        payload: dict[str, Any] = {"title": title, "body": body}
        issue_labels = _build_issue_labels(labels, normalized_source_period_type, include_period_label)
        if issue_labels:
            payload["labels"] = issue_labels
        if assignees:
            payload["assignees"] = assignees
        url = f"https://api.github.com/repos/{repo}/issues"
        _request_with_rate_limit_retry(
            requests.post,
            "POST",
            url,
            headers=headers,
            json=payload,
            timeout=ISSUE_SYNC_TIMEOUT_SEC,
        )
        created += 1
        existing_titles.add(title)
        existing_meta_keys.add(meta_key)

    return {"created": created, "skipped_existing": skipped_existing}


def _fetch_open_issue_index(repo: str, headers: dict[str, str]) -> tuple[set[str], set[tuple[str, str]]]:
    url = f"https://api.github.com/repos/{repo}/issues"
    response = _request_with_rate_limit_retry(
        requests.get,
        "GET",
        url,
        headers=headers,
        params={"state": "open", "per_page": 100},
        timeout=ISSUE_SYNC_TIMEOUT_SEC,
    )
    items: list[dict[str, Any]] = response.json()

    titles: set[str] = set()
    meta_keys: set[tuple[str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        if "pull_request" in item:
            continue
        title = item.get("title")
        if isinstance(title, str) and title:
            titles.add(title)

        body = item.get("body")
        if isinstance(body, str) and body:
            marker = _extract_meta_marker(body)
            if marker:
                meta_keys.add(marker)

    return titles, meta_keys

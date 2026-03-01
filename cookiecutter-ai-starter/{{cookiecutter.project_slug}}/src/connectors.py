"""Automatic data collection connectors."""

from __future__ import annotations

from pathlib import Path
import json
import os
import time
from typing import Any
from urllib.parse import urlencode
from datetime import datetime, timezone

import requests


FETCH_META_PATH = Path("logs") / "fetch_meta.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta_key(url: str, params: dict[str, Any] | None = None) -> str:
    if not params:
        return url
    return f"{url}?{urlencode(sorted((str(k), str(v)) for k, v in params.items()))}"


def _load_fetch_meta(path: Path | None = None) -> dict[str, dict[str, str]]:
    path = path or FETCH_META_PATH
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, dict):
            result[key] = {str(k): str(v) for k, v in value.items()}
    return result


def _save_fetch_meta(meta: dict[str, dict[str, str]], path: Path | None = None) -> None:
    path = path or FETCH_META_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _touch_access_meta(key: str, path: Path | None = None) -> None:
    path = path or FETCH_META_PATH
    meta = _load_fetch_meta(path)
    current = meta.get(key, {})
    current["accessed_at"] = _now_iso()
    meta[key] = current
    _save_fetch_meta(meta, path)


def _update_response_meta(response: requests.Response, key: str, path: Path | None = None) -> None:
    path = path or FETCH_META_PATH
    meta = _load_fetch_meta(path)
    current = meta.get(key, {})
    etag = response.headers.get("ETag")
    last_modified = response.headers.get("Last-Modified")
    if etag:
        current["etag"] = etag
    if last_modified:
        current["last_modified"] = last_modified
    current["accessed_at"] = _now_iso()
    meta[key] = current
    _save_fetch_meta(meta, path)


def _max_wait_sec() -> float:
    text = os.getenv("CONNECTOR_MAX_WAIT_SEC", "30").strip()
    try:
        return max(0.0, float(text))
    except ValueError:
        return 30.0


def _rate_limit_wait_seconds(response: requests.Response) -> float | None:
    is_429 = response.status_code == 429
    remaining = response.headers.get("X-RateLimit-Remaining", "").strip()
    is_github_limited = remaining == "0"
    if not (is_429 or is_github_limited):
        return None

    max_wait = _max_wait_sec()
    reset_text = response.headers.get("X-RateLimit-Reset", "").strip()
    if reset_text:
        try:
            reset_at = float(reset_text)
            wait = max(0.0, reset_at - time.time())
            return min(wait, max_wait)
        except ValueError:
            pass

    retry_after_text = response.headers.get("Retry-After", "").strip()
    if retry_after_text:
        try:
            wait = max(0.0, float(retry_after_text))
            return min(wait, max_wait)
        except ValueError:
            pass
    return None


def _get_with_retry(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> requests.Response:
    retries_text = os.getenv("CONNECTOR_RETRIES", "3").strip()
    backoff_text = os.getenv("CONNECTOR_BACKOFF_SEC", "0.5").strip()

    try:
        retries = max(1, int(retries_text))
    except ValueError:
        retries = 3

    try:
        backoff = max(0.0, float(backoff_text))
    except ValueError:
        backoff = 0.5

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
            wait = _rate_limit_wait_seconds(response)
            if wait is not None and attempt < retries:
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                raise
            time.sleep(backoff * (2 ** (attempt - 1)))

    if last_error:
        raise last_error
    raise RuntimeError("request failed")


def fetch_github_issues(repo: str, state: str = "open", limit: int = 20) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/issues"
    params = {"state": state, "per_page": limit}
    key = _meta_key(url, params)
    cached = _load_fetch_meta().get(key, {})
    headers: dict[str, str] = {}
    if cached.get("etag"):
        headers["If-None-Match"] = cached["etag"]
    if cached.get("last_modified"):
        headers["If-Modified-Since"] = cached["last_modified"]

    response = _get_with_retry(url, params=params, headers=headers or None, timeout=20)
    if response.status_code == 304:
        _touch_access_meta(key)
        return []

    _update_response_meta(response, key)
    items = response.json()

    entries: list[dict[str, Any]] = []
    for issue in items:
        if "pull_request" in issue:
            continue
        title = issue.get("title", "")
        body = issue.get("body", "")
        issue_url = issue.get("html_url", "")
        entries.append({"source": f"github:{repo}", "content": f"{title}\n{body}\n{issue_url}".strip()})
    return entries


def fetch_rss_feed(feed_url: str, limit: int = 20) -> list[dict[str, Any]]:
    key = _meta_key(feed_url)
    cached = _load_fetch_meta().get(key, {})
    headers: dict[str, str] = {}
    if cached.get("etag"):
        headers["If-None-Match"] = cached["etag"]
    if cached.get("last_modified"):
        headers["If-Modified-Since"] = cached["last_modified"]

    response = _get_with_retry(feed_url, headers=headers or None, timeout=20)
    if response.status_code == 304:
        _touch_access_meta(key)
        return []

    _update_response_meta(response, key)
    text = response.text

    items: list[dict[str, Any]] = []
    blocks = text.split("<item>")
    if len(blocks) == 1:
        blocks = text.split("<entry>")

    for block in blocks[1 : limit + 1]:
        title = _extract_tag(block, "title")
        link = _extract_tag(block, "link")
        desc = _extract_tag(block, "description") or _extract_tag(block, "summary")
        items.append({"source": f"rss:{feed_url}", "content": f"{title}\n{desc}\n{link}".strip()})
    return items


def fetch_survey_json(json_path: Path | str, content_field: str = "content") -> list[dict[str, Any]]:
    path = Path(json_path)
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)

    if not isinstance(data, list):
        return []

    entries: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "survey"))
        content = str(item.get(content_field, ""))
        if content:
            entries.append({"source": source, "content": content})
    return entries


def _extract_tag(block: str, tag: str) -> str:
    open_tag = f"<{tag}>"
    close_tag = f"</{tag}>"
    if open_tag in block and close_tag in block:
        start = block.find(open_tag) + len(open_tag)
        end = block.find(close_tag, start)
        return block[start:end].strip()
    return ""

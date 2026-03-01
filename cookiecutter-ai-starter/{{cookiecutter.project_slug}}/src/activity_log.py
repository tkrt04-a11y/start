"""Activity logging utilities with timestamps."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json


def _mask_string(value: str) -> str:
    if len(value) <= 6:
        return "***"
    return value[:2] + "***" + value[-2:]


def _mask_sensitive(data: Any) -> Any:
    if isinstance(data, dict):
        masked: dict[str, Any] = {}
        for key, value in data.items():
            lower_key = str(key).lower()
            if any(token in lower_key for token in ["token", "secret", "password", "api_key", "webhook"]):
                masked[key] = "***"
            elif isinstance(value, str) and ("ghp_" in value or value.startswith("sk-") or "https://" in value and "webhook" in lower_key):
                masked[key] = _mask_string(value)
            else:
                masked[key] = _mask_sensitive(value)
        return masked
    if isinstance(data, list):
        return [_mask_sensitive(item) for item in data]
    return data


def append_activity(
    event: str,
    details: dict[str, Any] | None = None,
    level: str = "info",
    log_path: Path | str = "logs/activity_history.jsonl",
) -> None:
    try:
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "level": level,
            "details": _mask_sensitive(details or {}),
        }
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        return


def read_recent_activities(
    limit: int = 200,
    log_path: Path | str = "logs/activity_history.jsonl",
) -> list[dict[str, Any]]:
    path = Path(log_path)
    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    records: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(records))

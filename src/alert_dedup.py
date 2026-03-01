"""Alert webhook deduplication helpers."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from datetime import timedelta
from typing import Any


_TIMESTAMP_PREFIX_PATTERN = re.compile(r"^\[[^\]]+\]\s*")
_WHITESPACE_PATTERN = re.compile(r"\s+")
DEFAULT_ALERT_DEDUP_TTL_SEC = 7 * 24 * 60 * 60


def _normalize_alert_message(line: str) -> str:
    message = _TIMESTAMP_PREFIX_PATTERN.sub("", line.strip())
    return _WHITESPACE_PATTERN.sub(" ", message).strip().lower()


def build_alert_signature(line: str) -> str:
    normalized = _normalize_alert_message(line)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    return utc.isoformat().replace("+00:00", "Z")


def get_alert_dedup_ttl_sec() -> int:
    text = os.getenv("ALERT_DEDUP_TTL_SEC", str(DEFAULT_ALERT_DEDUP_TTL_SEC)).strip()
    try:
        value = int(text)
    except ValueError:
        value = DEFAULT_ALERT_DEDUP_TTL_SEC
    return max(0, value)


def load_alert_dedup_state(path: Path | str) -> dict[str, str]:
    state_path = Path(path)
    if not state_path.exists():
        return {}

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    if isinstance(payload, dict):
        last_sent = payload.get("last_sent")
        if isinstance(last_sent, dict):
            return {
                str(signature): str(timestamp)
                for signature, timestamp in last_sent.items()
                if isinstance(signature, str) and isinstance(timestamp, str)
            }
    return {}


def save_alert_dedup_state(path: Path | str, last_sent_by_signature: dict[str, str]) -> None:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"last_sent": dict(last_sent_by_signature)}

    file_descriptor, temp_path = tempfile.mkstemp(
        prefix=f".{state_path.name}.",
        suffix=".tmp",
        dir=str(state_path.parent),
    )
    temp_file = Path(temp_path)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp_file.replace(state_path)
    finally:
        if temp_file.exists():
            temp_file.unlink(missing_ok=True)


def _prune_state_entries(state: dict[str, str], ttl_sec: int, now: datetime) -> tuple[dict[str, str], int]:
    if ttl_sec <= 0:
        return dict(state), 0

    cutoff = now - timedelta(seconds=ttl_sec)
    retained: dict[str, str] = {}
    removed_count = 0
    for signature, timestamp in state.items():
        parsed = _parse_timestamp(timestamp)
        if parsed is None or parsed >= cutoff:
            retained[signature] = timestamp
        else:
            removed_count += 1
    return retained, removed_count


def _load_state_with_prune(path: Path | str, ttl_sec: int, now: datetime) -> tuple[dict[str, str], int, int]:
    state = load_alert_dedup_state(path)
    pruned_state, removed_count = _prune_state_entries(state, ttl_sec=ttl_sec, now=now)
    if removed_count > 0:
        save_alert_dedup_state(path, pruned_state)
    return pruned_state, removed_count, len(state)


def prune_alert_dedup_state(
    path: Path | str,
    ttl_sec: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    effective_ttl = get_alert_dedup_ttl_sec() if ttl_sec is None else max(0, int(ttl_sec))
    _, removed_count, before_count = _load_state_with_prune(path, ttl_sec=effective_ttl, now=current)
    return {
        "state_path": str(Path(path)),
        "ttl_sec": effective_ttl,
        "entry_count_before": before_count,
        "entry_count_after": before_count - removed_count,
        "removed_count": removed_count,
    }


def should_emit_signature(last_sent_timestamp: str | None, cooldown_sec: int, now: datetime) -> bool:
    if cooldown_sec <= 0:
        return True
    last_sent = _parse_timestamp(last_sent_timestamp)
    if last_sent is None:
        return True
    elapsed_sec = (now - last_sent).total_seconds()
    return elapsed_sec >= cooldown_sec


def should_emit_and_update_state(
    state_path: Path | str,
    line: str,
    cooldown_sec: int = 600,
    ttl_sec: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    effective_ttl = get_alert_dedup_ttl_sec() if ttl_sec is None else max(0, int(ttl_sec))
    signature = build_alert_signature(line)
    state, pruned_count, _ = _load_state_with_prune(state_path, ttl_sec=effective_ttl, now=current)
    last_sent = state.get(signature)
    send = should_emit_signature(last_sent, cooldown_sec=max(0, int(cooldown_sec)), now=current)

    result: dict[str, Any] = {
        "send": send,
        "signature": signature,
        "last_sent": last_sent,
        "cooldown_sec": max(0, int(cooldown_sec)),
        "ttl_sec": effective_ttl,
        "pruned_count": pruned_count,
    }
    if send:
        sent_at = _format_timestamp(current)
        state[signature] = sent_at
        save_alert_dedup_state(state_path, state)
        result["sent_at"] = sent_at
    return result


def summarize_alert_dedup_state(path: Path | str, top_n: int = 5, signature_preview_length: int = 12) -> dict[str, Any]:
    current = datetime.now(timezone.utc)
    ttl_sec = get_alert_dedup_ttl_sec()
    state, pruned_count, _ = _load_state_with_prune(path, ttl_sec=ttl_sec, now=current)
    rows: list[tuple[str, str, datetime | None]] = []
    for signature, timestamp in state.items():
        rows.append((signature, timestamp, _parse_timestamp(timestamp)))

    rows.sort(
        key=lambda item: (
            item[2] is not None,
            item[2] or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    parsed_timestamps = [parsed for _, _, parsed in rows if parsed is not None]
    oldest = _format_timestamp(min(parsed_timestamps)) if parsed_timestamps else ""
    newest = _format_timestamp(max(parsed_timestamps)) if parsed_timestamps else ""

    top_signatures: list[dict[str, str]] = []
    limit = max(0, int(top_n))
    preview_length = max(4, int(signature_preview_length))
    for signature, timestamp, _ in rows[:limit]:
        preview = signature[:preview_length]
        if len(signature) > preview_length:
            preview = f"{preview}..."
        top_signatures.append(
            {
                "signature": signature,
                "signature_preview": preview,
                "timestamp": timestamp,
            }
        )

    state_path = Path(path)
    return {
        "state_path": str(state_path),
        "exists": state_path.exists(),
        "ttl_sec": ttl_sec,
        "pruned_count": pruned_count,
        "entry_count": len(state),
        "oldest_timestamp": oldest,
        "newest_timestamp": newest,
        "top_signatures": top_signatures,
    }


def reset_alert_dedup_state(path: Path | str, backup: bool = False) -> dict[str, Any]:
    state_path = Path(path)
    ttl_sec = get_alert_dedup_ttl_sec()
    current = datetime.now(timezone.utc)
    before, pruned_count, before_prune_count = _load_state_with_prune(state_path, ttl_sec=ttl_sec, now=current)
    existed = state_path.exists()

    backup_path = ""
    if existed and backup:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup_file = state_path.with_name(f"{state_path.stem}-{timestamp}.bak{state_path.suffix}")
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(state_path, backup_file)
        backup_path = str(backup_file)

    save_alert_dedup_state(state_path, {})
    return {
        "state_path": str(state_path),
        "existed": existed,
        "ttl_sec": ttl_sec,
        "pruned_count": pruned_count,
        "entry_count_before_prune": before_prune_count,
        "entry_count_before": len(before),
        "entry_count_after": 0,
        "backup_path": backup_path,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="Alert webhook deduplication state updater")
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--line", required=True)
    parser.add_argument("--cooldown-sec", type=int, default=600)
    parser.add_argument("--ttl-sec", type=int, default=None)
    parser.add_argument("--now", default="")
    args = parser.parse_args()

    now = _parse_timestamp(args.now) if args.now else None
    result = should_emit_and_update_state(
        state_path=args.state_path,
        line=args.line,
        cooldown_sec=max(0, int(args.cooldown_sec)),
        ttl_sec=args.ttl_sec,
        now=now,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
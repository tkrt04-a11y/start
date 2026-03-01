"""Data retention and archive utilities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import json
import os
import re
import shutil


def _parse_iso_timestamp(value: str | None) -> datetime | None:
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
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _retention_days() -> int:
    text = os.getenv("RETENTION_DAYS", "90").strip()
    try:
        return max(0, int(text))
    except ValueError:
        return 90


def _load_json_array(path: Path) -> list[Any]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, list):
                return loaded
    except (json.JSONDecodeError, OSError):
        return []
    return []


def _write_json(path: Path, payload: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _append_lines(path: Path, lines: list[str]) -> None:
    if not lines:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        if path.exists() and path.stat().st_size > 0:
            f.write("\n")
        f.write("\n".join(lines))


def _rewrite_lines(path: Path, lines: list[str]) -> None:
    if not path.exists():
        return
    with path.open("w", encoding="utf-8") as f:
        if lines:
            f.write("\n".join(lines) + "\n")


def _archive_date(now: datetime) -> str:
    return now.strftime("%Y%m%d")


def run_retention(base_dir: Path | str = ".") -> dict[str, Any]:
    root = Path(base_dir)
    now = datetime.now()
    days = _retention_days()
    cutoff = now - timedelta(days=days)
    archive_dir = root / "archive"
    archive_tag = _archive_date(now)

    collected_moved = 0
    collected_kept = 0
    collected_path = root / "collected_data.json"
    if collected_path.exists():
        entries = _load_json_array(collected_path)
        moved_entries: list[Any] = []
        kept_entries: list[Any] = []
        for entry in entries:
            timestamp = _parse_iso_timestamp(str(entry.get("collected_at", "")) if isinstance(entry, dict) else "")
            if timestamp and timestamp < cutoff:
                moved_entries.append(entry)
            else:
                kept_entries.append(entry)

        if moved_entries:
            archive_path = archive_dir / f"collected_data-{archive_tag}.json"
            archived_entries = _load_json_array(archive_path)
            archived_entries.extend(moved_entries)
            _write_json(archive_path, archived_entries)
        _write_json(collected_path, kept_entries)
        collected_moved = len(moved_entries)
        collected_kept = len(kept_entries)

    history_moved = 0
    history_kept = 0
    history_path = root / "logs" / "activity_history.jsonl"
    if history_path.exists():
        kept_lines: list[str] = []
        moved_lines: list[str] = []
        with history_path.open("r", encoding="utf-8") as f:
            for raw_line in f.read().splitlines():
                text = raw_line.strip()
                if not text:
                    continue
                timestamp: datetime | None = None
                try:
                    payload = json.loads(text)
                    if isinstance(payload, dict):
                        timestamp = _parse_iso_timestamp(str(payload.get("timestamp", "")))
                except json.JSONDecodeError:
                    timestamp = None

                if timestamp and timestamp < cutoff:
                    moved_lines.append(raw_line)
                else:
                    kept_lines.append(raw_line)

        if moved_lines:
            _append_lines(archive_dir / f"activity_history-{archive_tag}.jsonl", moved_lines)
        _rewrite_lines(history_path, kept_lines)
        history_moved = len(moved_lines)
        history_kept = len(kept_lines)

    alerts_moved = 0
    alerts_kept = 0
    alerts_path = root / "logs" / "alerts.log"
    if alerts_path.exists():
        kept_lines: list[str] = []
        moved_lines: list[str] = []
        pattern = re.compile(r"^\[([^\]]+)\]")
        with alerts_path.open("r", encoding="utf-8") as f:
            for raw_line in f.read().splitlines():
                match = pattern.match(raw_line)
                timestamp = _parse_iso_timestamp(match.group(1)) if match else None
                if timestamp and timestamp < cutoff:
                    moved_lines.append(raw_line)
                else:
                    kept_lines.append(raw_line)

        if moved_lines:
            _append_lines(archive_dir / f"alerts-{archive_tag}.log", moved_lines)
        _rewrite_lines(alerts_path, kept_lines)
        alerts_moved = len(moved_lines)
        alerts_kept = len(kept_lines)

    metrics_moved = 0
    metrics_kept = 0
    metrics_archive_dir = archive_dir / "metrics"
    logs_dir = root / "logs"
    if logs_dir.exists():
        for metrics_path in sorted(logs_dir.glob("*-metrics-*.json")):
            try:
                modified_at = datetime.fromtimestamp(metrics_path.stat().st_mtime)
            except OSError:
                metrics_kept += 1
                continue

            if modified_at < cutoff:
                metrics_archive_dir.mkdir(parents=True, exist_ok=True)
                destination = metrics_archive_dir / metrics_path.name
                if destination.exists():
                    stem = metrics_path.stem
                    suffix = metrics_path.suffix
                    collision_index = 1
                    while destination.exists():
                        destination = metrics_archive_dir / f"{stem}-{archive_tag}-{collision_index}{suffix}"
                        collision_index += 1
                try:
                    shutil.move(str(metrics_path), str(destination))
                    metrics_moved += 1
                except OSError:
                    metrics_kept += 1
            else:
                metrics_kept += 1

    total_moved = collected_moved + history_moved + alerts_moved + metrics_moved
    total_kept = collected_kept + history_kept + alerts_kept + metrics_kept
    return {
        "retention_days": days,
        "cutoff": cutoff.isoformat(timespec="seconds"),
        "collected_data": {"moved": collected_moved, "kept": collected_kept},
        "activity_history": {"moved": history_moved, "kept": history_kept},
        "alerts": {"moved": alerts_moved, "kept": alerts_kept},
        "metrics": {"moved": metrics_moved, "kept": metrics_kept},
        "total": {"moved": total_moved, "kept": total_kept},
    }

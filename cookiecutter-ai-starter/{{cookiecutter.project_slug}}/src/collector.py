"""Placeholder collector included in cookiecutter template.

This file mirrors the implementation in the root of the repository; users
can later remove or extend it as needed.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json
import re


class DataCollector:
    def __init__(self, storage_path: Path | str = "collected_data.json"):
        self.storage_path = Path(storage_path)

    def collect(self, source: str, content: str) -> None:
        data = self._load()
        key = self._dedup_key(source, content)
        for existing in data:
            if self._dedup_key(str(existing.get("source", "")), str(existing.get("content", ""))) == key:
                return
        entry: dict[str, Any] = {
            "source": source,
            "content": content,
            "collected_at": datetime.now().isoformat(timespec="seconds"),
        }
        data.append(entry)
        self._save(data)

    def _dedup_key(self, source: str, content: str) -> str:
        normalized_source = re.sub(r"\s+", " ", source.strip().lower())
        normalized_content = re.sub(r"\s+", " ", content.strip().lower())
        return f"{normalized_source}::{normalized_content}"

    def _load(self) -> list[dict[str, Any]]:
        if self.storage_path.exists():
            with self.storage_path.open("r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return []
        return []

    def _save(self, data: list[dict[str, Any]]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

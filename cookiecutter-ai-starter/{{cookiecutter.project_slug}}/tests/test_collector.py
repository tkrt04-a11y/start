import json
from pathlib import Path

import pytest

from src.collector import DataCollector


def test_collect_appends_entry(tmp_path: Path):
    storage = tmp_path / "data.json"
    collector = DataCollector(storage)

    collector.collect("foo", "bar")
    with storage.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert data[0]["source"] == "foo"
    assert data[0]["content"] == "bar"
    assert "collected_at" in data[0]


def test_collect_skips_duplicate_entries(tmp_path: Path):
    storage = tmp_path / "data.json"
    collector = DataCollector(storage)

    collector.collect("foo", "bar")
    collector.collect("foo", "  bar  ")

    with storage.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data) == 1

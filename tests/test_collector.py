import json
from pathlib import Path

import pytest

from src.collector import DataCollector


def test_collect_appends_entry(tmp_path: Path):
    storage = tmp_path / "data.json"
    collector = DataCollector(storage)

    # start with an empty file implicitly
    collector.collect("test-source", "some information")
    collector.collect("another", "more info")

    # read back and verify
    with storage.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, list)
    assert data[0]["source"] == "test-source"
    assert data[0]["content"] == "some information"
    assert "collected_at" in data[0]
    assert data[1]["source"] == "another"
    assert data[1]["content"] == "more info"
    assert "collected_at" in data[1]


def test_collect_creates_file_on_invalid_json(tmp_path: Path):
    storage = tmp_path / "broken.json"
    storage.write_text("not a json")
    collector = DataCollector(storage)
    # should not raise, should overwrite invalid content
    collector.collect("src", "c")
    with storage.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert data[0]["source"] == "src"
    assert "collected_at" in data[0]


def test_collect_skips_duplicate_entries(tmp_path: Path):
    storage = tmp_path / "data.json"
    collector = DataCollector(storage)

    collector.collect("rss:https://example", "Same content")
    collector.collect("rss:https://example", "  Same   content  ")

    with storage.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data) == 1


def test_handle_collect_cli(monkeypatch, tmp_path: Path, capsys):
    # simulate running main.handle_collect via sys.argv style
    from src import main

    storage = tmp_path / "cli.json"
    # monkeypatch DataCollector to use our temporary path
    class DummyCollector:
        def __init__(self, path=storage):
            self._path = path
            if self._path.exists():
                self._path.unlink()

        def collect(self, source, content):
            # write to file directly so we can assert later
            with self._path.open("w", encoding="utf-8") as f:
                json.dump({"source": source, "content": content}, f)

    monkeypatch.setattr(main, "DataCollector", DummyCollector)

    # simulate arguments passed
    main.handle_collect(["cli-src", "cli-content"])
    captured = capsys.readouterr()
    assert "Information collected" in captured.out
    # verify file
    with storage.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["source"] == "cli-src"
    assert data["content"] == "cli-content"

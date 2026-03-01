import json
import sys
from pathlib import Path

import pytest

from src import analyzer


def test_load_entries_nonexistent(tmp_path: Path):
    path = tmp_path / "nope.json"
    assert analyzer.load_entries(path) == []


def test_load_entries_invalid_json(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("not json")
    assert analyzer.load_entries(path) == []


def test_summarize_and_pretty_print(capsys: pytest.CaptureFixture):
    entries = [
        {"source": "a", "content": "x"},
        {"source": "b", "content": "y"},
        {"source": "a", "content": "z"},
    ]
    summary = analyzer.summarize_by_source(entries)
    assert summary == {"a": 2, "b": 1}
    analyzer.pretty_print_summary(summary)
    captured = capsys.readouterr()
    assert "Entries by source" in captured.out
    assert "a: 2" in captured.out
    assert "b: 1" in captured.out


def test_analyze_cli(monkeypatch, capsys, tmp_path: Path):
    # Prepare a fake data file
    path = tmp_path / "collected_data.json"
    data = [{"source": "s", "content": "c"}]
    path.write_text(json.dumps(data))

    # monkeypatch the function used by main (it was imported directly)
    from src import main
    monkeypatch.setattr(main, "load_entries", lambda p=None: data)

    from src import main
    monkeypatch.setenv("OPENAI_API_KEY", "ignored")
    monkeypatch.setattr(sys, "argv", ["prog", "analyze"])
    main.main()
    captured = capsys.readouterr()
    assert "Entries by source" in captured.out


def test_generate_ai_summary(monkeypatch):
    class DummyCompletions:
        @staticmethod
        def create(model, messages, temperature=0):
            class Msg:
                content = "theme summary"

            class Choice:
                message = Msg()

            class Resp:
                choices = [Choice()]

            return Resp()

    class DummyChat:
        completions = DummyCompletions()

    class DummyClient:
        chat = DummyChat()

    monkeypatch.setattr(analyzer.models, "get_openai_client", lambda key: DummyClient())
    text = analyzer.generate_ai_summary([{"source": "x", "content": "y"}], api_key="k")
    assert "theme summary" in text


def test_generate_fallback_summary():
    text = analyzer.generate_fallback_summary(
        [
            {"source": "rss:sample", "content": "need better documentation and tests"},
            {"source": "rss:sample", "content": "better setup and docs"},
        ]
    )
    assert "Fallback summary" in text
    assert "rss:sample" in text

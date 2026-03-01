import json
from pathlib import Path

import pytest

from src import analyzer


def test_load_entries(tmp_path: Path):
    path = tmp_path / "data.json"
    assert analyzer.load_entries(path) == []


def test_summarize_and_pretty_print(capsys: pytest.CaptureFixture):
    entries = [{"source": "x"}, {"source": "y"}, {"source": "x"}]
    summary = analyzer.summarize_by_source(entries)
    assert summary == {"x": 2, "y": 1}
    analyzer.pretty_print_summary(summary)
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

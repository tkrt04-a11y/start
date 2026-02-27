import os
import pytest
from src import main


def test_missing_api_key(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    main.main()
    captured = capsys.readouterr()
    assert "Please set OPENAI_API_KEY" in captured.out

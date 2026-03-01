import os
import sys
import pytest
from src import main


def test_missing_api_key(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    main.main()
    captured = capsys.readouterr()
    assert "Please set OPENAI_API_KEY" in captured.out


def test_main_collect_dispatch(monkeypatch, capsys, tmp_path):
    # ensure that invoking ``main`` with the "collect" argument uses the
    # collector logic and does not attempt to contact OpenAI.
    from src import main as main_module

    # intercept the collector so we don't write to the real filesystem
    called = {}

    class DummyCollector:
        def __init__(self, *args, **kwargs):
            called["init_args"] = (args, kwargs)

        def collect(self, source, content):
            called["source"] = source
            called["content"] = content

    monkeypatch.setattr(main_module, "DataCollector", DummyCollector)

    monkeypatch.setenv("OPENAI_API_KEY", "unused")
    monkeypatch.setattr(sys, "argv", ["prog", "collect", "foo", "bar"])
    main_module.main()
    captured = capsys.readouterr()
    assert "Information collected" in captured.out
    assert called["source"] == "foo"
    assert called["content"] == "bar"


def test_main_apply_insights_dry_run_summary_new_file(monkeypatch, tmp_path, capsys):
    from src import main as main_module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main_module, "load_entries", lambda: [{"source": "s", "content": "c"}])
    monkeypatch.setattr(main_module, "summarize_by_source", lambda e: {"s": 1})
    monkeypatch.setattr(main_module, "extract_spotlight_action_items_from_markdown", lambda md: [])
    monkeypatch.setattr(main_module, "extract_promoted_actions_from_markdown", lambda md: [])

    main_module.handle_apply_insights(["--dry-run"])
    captured = capsys.readouterr()
    assert "backlog: new_file (" in captured.out
    assert "instructions: new_file (" in captured.out


def test_main_apply_insights_dry_run_summary_unchanged(monkeypatch, tmp_path, capsys):
    from src import main as main_module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main_module, "load_entries", lambda: [{"source": "s", "content": "c"}])
    monkeypatch.setattr(main_module, "summarize_by_source", lambda e: {"s": 1})
    monkeypatch.setattr(main_module, "extract_spotlight_action_items_from_markdown", lambda md: [])
    monkeypatch.setattr(main_module, "extract_promoted_actions_from_markdown", lambda md: [])

    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".github" / "instructions").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "improvement_backlog.md").write_text(
        main_module.generate_backlog_markdown({"s": 1}, "", spotlight_actions=[], promoted_actions=[]),
        encoding="utf-8",
    )
    (tmp_path / ".github" / "instructions" / "common.instructions.md").write_text(
        main_module.render_instruction_markdown("", ["s"]),
        encoding="utf-8",
    )

    main_module.handle_apply_insights(["--dry-run"])
    captured = capsys.readouterr()
    assert "backlog: unchanged (+0/-0 lines)" in captured.out
    assert "instructions: unchanged (+0/-0 lines)" in captured.out


def test_main_apply_insights_dry_run_summary_changed(monkeypatch, tmp_path, capsys):
    from src import main as main_module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main_module, "load_entries", lambda: [{"source": "s", "content": "c"}])
    monkeypatch.setattr(main_module, "summarize_by_source", lambda e: {"s": 1})
    monkeypatch.setattr(main_module, "extract_spotlight_action_items_from_markdown", lambda md: [])
    monkeypatch.setattr(main_module, "extract_promoted_actions_from_markdown", lambda md: [])

    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".github" / "instructions").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "improvement_backlog.md").write_text("old backlog\n", encoding="utf-8")
    (tmp_path / ".github" / "instructions" / "common.instructions.md").write_text("old instructions\n", encoding="utf-8")

    main_module.handle_apply_insights(["--dry-run"])
    captured = capsys.readouterr()
    assert "backlog: changed (" in captured.out
    assert "instructions: changed (" in captured.out

def test_main_retention_dispatch(monkeypatch, capsys):
    from src import main as main_module

    monkeypatch.setattr(
        main_module,
        "run_retention",
        lambda: {
            "retention_days": 90,
            "collected_data": {"moved": 1, "kept": 2},
            "activity_history": {"moved": 3, "kept": 4},
            "alerts": {"moved": 5, "kept": 6},
            "metrics": {"moved": 7, "kept": 8},
            "total": {"moved": 16, "kept": 20},
        },
    )
    monkeypatch.setattr(sys, "argv", ["prog", "retention"])

    main_module.main()
    captured = capsys.readouterr()
    assert "Retention completed." in captured.out
    assert "metrics: moved=7 kept=8" in captured.out
    assert "total: moved=16 kept=20" in captured.out


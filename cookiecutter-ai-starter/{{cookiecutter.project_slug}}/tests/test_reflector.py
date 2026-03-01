from pathlib import Path

from src import reflector


def test_generate_backlog_markdown():
    text = reflector.generate_backlog_markdown({"a": 2}, "ai summary")
    assert "Improvement Backlog" in text
    assert "a: 2" in text
    assert "## Promoted This Week" in text
    assert "## Spotlight Actions" in text


def test_write_backlog(tmp_path: Path):
    output = tmp_path / "docs" / "improvement_backlog.md"
    path = reflector.write_backlog({"s": 1}, output_path=output)
    assert path.exists()


def test_write_backlog_with_spotlight_actions(tmp_path: Path):
    output = tmp_path / "docs" / "improvement_backlog.md"
    path = reflector.write_backlog(
        {"s": 1},
        spotlight_actions=["Action one"],
        output_path=output,
    )
    content = path.read_text(encoding="utf-8")
    assert "- [ ] Action one" in content


def test_write_backlog_with_spotlight_actions_sorted_by_priority(tmp_path: Path):
    output = tmp_path / "docs" / "improvement_backlog.md"
    path = reflector.write_backlog(
        {"s": 1},
        spotlight_actions=["[Low] low", "[High] high", "[Med] med"],
        output_path=output,
    )
    lines = path.read_text(encoding="utf-8").splitlines()
    spotlight_lines = [line for line in lines if line.startswith("- [ ] [")]
    assert spotlight_lines[:3] == [
        "- [ ] [High] high",
        "- [ ] [Med] med",
        "- [ ] [Low] low",
    ]


def test_write_backlog_with_promoted_actions(tmp_path: Path):
    output = tmp_path / "docs" / "improvement_backlog.md"
    path = reflector.write_backlog(
        {"s": 1},
        promoted_actions=["Promoted X", "Promoted X", "Promoted Y"],
        output_path=output,
    )
    content = path.read_text(encoding="utf-8")
    assert "## Promoted This Week" in content
    assert content.count("- [ ] Promoted X") == 1
    assert "- [ ] Promoted Y" in content


def test_update_instruction_file(tmp_path: Path):
    instruction = tmp_path / "common.instructions.md"
    instruction.write_text("base", encoding="utf-8")
    path = reflector.update_instruction_file(["github"], instruction_path=instruction)
    assert path.exists()
    assert "auto-insights:start" in path.read_text(encoding="utf-8")

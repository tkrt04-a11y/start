from pathlib import Path

from src import env_tools


def test_ensure_env_from_example_creates_and_adds_keys(tmp_path: Path):
    example = tmp_path / ".env.example"
    target = tmp_path / ".env"
    example.write_text("A=1\nB=2\n", encoding="utf-8")

    result = env_tools.ensure_env_from_example(example_path=example, env_path=target)
    assert result["created"] == 1
    assert result["added"] == 2
    assert "A=1" in target.read_text(encoding="utf-8")


def test_ensure_env_from_example_adds_only_missing_keys(tmp_path: Path):
    example = tmp_path / ".env.example"
    target = tmp_path / ".env"
    example.write_text("A=1\nB=2\n", encoding="utf-8")
    target.write_text("A=9\n", encoding="utf-8")

    result = env_tools.ensure_env_from_example(example_path=example, env_path=target)
    assert result["created"] == 0
    assert result["added"] == 1
    text = target.read_text(encoding="utf-8")
    assert "A=9" in text
    assert "B=2" in text

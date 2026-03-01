from datetime import date, datetime

from src import reporter


def test_generate_weekly_report_markdown():
    text = reporter.generate_weekly_report_markdown(
        entries=[{"source": "a", "content": "x"}],
        source_summary={"a": 1},
        ai_summary="summary",
        today=date(2026, 2, 28),
    )
    assert "Weekly Report (2026-W09)" in text
    assert "Total entries: 1" in text


def test_write_weekly_report(tmp_path):
    path = reporter.write_weekly_report(
        entries=[{"source": "a", "content": "x"}],
        source_summary={"a": 1},
        ai_summary="summary",
        output_dir=tmp_path,
        today=date(2026, 2, 28),
    )
    assert path.exists()
    assert (tmp_path / "latest_weekly_report.md").exists()
    assert (tmp_path / "weekly-report-2026-W09.html").exists()
    assert (tmp_path / "latest_weekly_report.html").exists()


def test_generate_monthly_report_markdown():
    text = reporter.generate_monthly_report_markdown(
        entries=[{"source": "a", "content": "x"}],
        source_summary={"a": 1},
        ai_summary="monthly summary",
        month_label="2026-02",
        today=date(2026, 2, 28),
    )
    assert "Monthly Report (2026-02)" in text
    assert "Target month: 2026-02" in text
    assert "Total entries: 1" in text
    assert "monthly summary" in text


def test_generate_monthly_report_markdown_with_delta_and_spotlight():
    text = reporter.generate_monthly_report_markdown(
        entries=[{"source": "github:owner/repo", "content": "x"}],
        source_summary={"github:owner/repo": 5, "rss:feed": 1},
        previous_summary={"github:owner/repo": 2, "rss:feed": 4},
        ai_summary="monthly summary",
        month_label="2026-02",
        today=date(2026, 2, 28),
    )
    assert "Period-over-Period Delta (vs previous month: 2026-01)" in text
    assert "github:owner/repo: +3" in text
    assert "rss:feed: -3" in text
    assert "Spotlight (Top 3 Changes)" in text
    assert "Action:" in text


def test_generate_monthly_report_markdown_adds_promotable_actions_for_high_delta():
    text = reporter.generate_monthly_report_markdown(
        entries=[{"source": "github:owner/repo", "content": "x"}],
        source_summary={"github:owner/repo": 30},
        previous_summary={"github:owner/repo": 0},
        ai_summary="monthly summary",
        month_label="2026-02",
        today=date(2026, 2, 28),
    )
    assert "## Promotable Actions" in text
    assert "[Promoted] Review top issues and convert recurring requests into template tasks." in text


def test_write_monthly_report(tmp_path):
    path = reporter.write_monthly_report(
        entries=[{"source": "a", "content": "x"}],
        source_summary={"a": 1},
        ai_summary="summary",
        month_label="2026-02",
        output_dir=tmp_path,
        today=date(2026, 2, 28),
    )
    assert path.exists()
    assert (tmp_path / "latest_monthly_report.md").exists()
    assert (tmp_path / "monthly-report-2026-02.html").exists()
    assert (tmp_path / "latest_monthly_report.html").exists()


def test_filter_entries_by_days():
    now = datetime(2026, 2, 28, 12, 0, 0)
    entries = [
        {"source": "a", "content": "x", "collected_at": "2026-02-28T10:00:00"},
        {"source": "b", "content": "y", "collected_at": "2026-02-20T10:00:00"},
        {"source": "legacy", "content": "z"},
    ]
    filtered = reporter.filter_entries_by_days(entries, days=7, now=now)
    assert len(filtered) == 2


def test_compute_source_deltas():
    deltas = reporter.compute_source_deltas({"a": 5, "b": 1}, {"a": 3, "c": 2})
    assert deltas["a"] == 2
    assert deltas["b"] == 1
    assert deltas["c"] == -2


def test_generate_weekly_report_markdown_with_delta_section():
    text = reporter.generate_weekly_report_markdown(
        entries=[{"source": "a", "content": "x"}],
        source_summary={"a": 5},
        previous_summary={"a": 3},
        period_days=7,
        ai_summary="summary",
        today=date(2026, 2, 28),
    )
    assert "Period-over-Period Delta" in text
    assert "a: +2" in text
    assert "Spotlight (Top 3 Changes)" in text
    assert "Action:" in text


def test_generate_weekly_report_markdown_promotes_high_actions():
    text = reporter.generate_weekly_report_markdown(
        entries=[{"source": "github:owner/repo", "content": "x"}],
        source_summary={"github:owner/repo": 30},
        previous_summary={"github:owner/repo": 0},
        period_days=7,
        ai_summary="summary",
        today=date(2026, 2, 28),
    )
    assert "[Promoted] Review top issues and convert recurring requests into template tasks." in text


def test_top_delta_sources():
    ranked = reporter.top_delta_sources({"a": 1, "b": -5, "c": 3, "d": -2}, limit=3)
    assert ranked[0] == ("b", -5)
    assert len(ranked) == 3


def test_recommend_action_for_source():
    action = reporter.recommend_action_for_source("github:owner/repo", 3)
    assert "issues" in action


def test_extract_spotlight_actions_from_markdown():
    md = """
## Spotlight (Top 3 Changes)
- github:x: +3 | Action: Do action one.
- rss:y: -1 | Action: Do action two.

## AI / Heuristic Summary
text
"""
    actions = reporter.extract_spotlight_actions_from_markdown(md)
    assert actions == ["Do action one.", "Do action two."]


def test_extract_spotlight_action_items_from_markdown_with_priority():
    md = """
## Spotlight (Top 3 Changes)
- github:x: +30 | Action: Do action high.
- rss:y: +7 | Action: Do action med.
- manual: +1 | Action: Do action low.
"""
    items = reporter.extract_spotlight_action_items_from_markdown(md)
    assert items == [
        {"action": "Do action high.", "priority": "High"},
        {"action": "Do action med.", "priority": "Med"},
        {"action": "Do action low.", "priority": "Low"},
    ]


def test_extract_promoted_actions_from_markdown():
    md = """
## Action Items
- [ ] [Promoted] Do promoted one.
- [ ] [Promoted] Do promoted two.
- [ ] Normal action.
"""
    actions = reporter.extract_promoted_actions_from_markdown(md)
    assert actions == ["Do promoted one.", "Do promoted two."]


def test_extract_monthly_promoted_actions_from_markdown():
    md = """
## Promotable Actions
- [ ] [Promoted] Do monthly promoted one.
- [ ] [Promoted] Do monthly promoted two.

## AI / Heuristic Summary
summary
"""
    actions = reporter.extract_monthly_promoted_actions_from_markdown(md)
    assert actions == ["Do monthly promoted one.", "Do monthly promoted two."]

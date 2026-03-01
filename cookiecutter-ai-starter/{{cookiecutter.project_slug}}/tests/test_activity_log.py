from pathlib import Path

from src import activity_log


def test_append_and_read_recent(tmp_path: Path):
    log_path = tmp_path / "activity_history.jsonl"

    activity_log.append_activity("event_a", {"x": 1}, log_path=log_path)
    activity_log.append_activity("event_b", {"y": 2}, log_path=log_path)

    rows = activity_log.read_recent_activities(limit=10, log_path=log_path)
    assert len(rows) == 2
    assert rows[0]["event"] == "event_b"
    assert "timestamp" in rows[0]


def test_append_masks_sensitive_details(tmp_path: Path):
    log_path = tmp_path / "activity_history.jsonl"

    activity_log.append_activity(
        "event_sensitive",
        {"api_key": "sk-123456789", "token": "ghp_abcdef", "normal": "ok"},
        log_path=log_path,
    )

    rows = activity_log.read_recent_activities(limit=10, log_path=log_path)
    details = rows[0]["details"]
    assert details["api_key"] == "***"
    assert details["token"] == "***"
    assert details["normal"] == "ok"

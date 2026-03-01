import json
from datetime import datetime, timedelta
import os

from src.retention import run_retention


def _iso_days_ago(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")


def test_run_retention_moves_old_entries_and_rewrites_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RETENTION_DAYS", "90")

    collected = [
        {"source": "old", "content": "x", "collected_at": _iso_days_ago(120)},
        {"source": "new", "content": "y", "collected_at": _iso_days_ago(5)},
    ]
    (tmp_path / "collected_data.json").write_text(json.dumps(collected, ensure_ascii=False), encoding="utf-8")

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    activity_lines = [
        json.dumps({"timestamp": _iso_days_ago(130), "event": "old"}, ensure_ascii=False),
        json.dumps({"timestamp": _iso_days_ago(1), "event": "new"}, ensure_ascii=False),
    ]
    (logs_dir / "activity_history.jsonl").write_text("\n".join(activity_lines) + "\n", encoding="utf-8")

    alert_lines = [
        f"[{_iso_days_ago(150)}] WARNING old alert",
        f"[{_iso_days_ago(2)}] WARNING recent alert",
        "line without timestamp",
    ]
    (logs_dir / "alerts.log").write_text("\n".join(alert_lines) + "\n", encoding="utf-8")

    old_metrics_path = logs_dir / "daily-metrics-20200101-000000.json"
    old_metrics_path.write_text('{"pipeline":"daily","success":true}', encoding="utf-8")
    old_timestamp = (datetime.now() - timedelta(days=150)).timestamp()
    os.utime(old_metrics_path, (old_timestamp, old_timestamp))

    recent_metrics_path = logs_dir / "weekly-metrics-20991231-235959.json"
    recent_metrics_path.write_text('{"pipeline":"weekly","success":true}', encoding="utf-8")

    result = run_retention()

    assert result["collected_data"]["moved"] == 1
    assert result["collected_data"]["kept"] == 1
    assert result["activity_history"]["moved"] == 1
    assert result["activity_history"]["kept"] == 1
    assert result["alerts"]["moved"] == 1
    assert result["alerts"]["kept"] == 2
    assert result["metrics"]["moved"] == 1
    assert result["metrics"]["kept"] == 1
    assert result["total"]["moved"] == 4
    assert result["total"]["kept"] == 5

    kept_collected = json.loads((tmp_path / "collected_data.json").read_text(encoding="utf-8"))
    assert len(kept_collected) == 1
    assert kept_collected[0]["source"] == "new"

    archive_dir = tmp_path / "archive"
    collected_archives = list(archive_dir.glob("collected_data-*.json"))
    activity_archives = list(archive_dir.glob("activity_history-*.jsonl"))
    alerts_archives = list(archive_dir.glob("alerts-*.log"))
    metrics_archives = list((archive_dir / "metrics").glob("*-metrics-*.json"))
    assert len(collected_archives) == 1
    assert len(activity_archives) == 1
    assert len(alerts_archives) == 1
    assert len(metrics_archives) == 1

    moved_collected = json.loads(collected_archives[0].read_text(encoding="utf-8"))
    assert len(moved_collected) == 1
    assert moved_collected[0]["source"] == "old"
    assert not old_metrics_path.exists()
    assert recent_metrics_path.exists()


def test_run_retention_uses_default_when_env_invalid(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RETENTION_DAYS", "not-a-number")
    (tmp_path / "collected_data.json").write_text("[]", encoding="utf-8")

    result = run_retention()
    assert result["retention_days"] == 90

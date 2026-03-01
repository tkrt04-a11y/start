from datetime import datetime, timedelta, timezone

from src.alert_dedup import (
    build_alert_signature,
    get_alert_dedup_ttl_sec,
    load_alert_dedup_state,
    prune_alert_dedup_state,
    reset_alert_dedup_state,
    save_alert_dedup_state,
    should_emit_and_update_state,
    summarize_alert_dedup_state,
)


def test_build_alert_signature_ignores_timestamp() -> None:
    line1 = "[2026-03-01T10:00:00] WARNING daily pipeline: promoted actions below threshold (0 < 1)"
    line2 = "[2026-03-01T10:05:00] WARNING daily pipeline: promoted actions below threshold (0 < 1)"

    assert build_alert_signature(line1) == build_alert_signature(line2)


def test_should_emit_and_update_state_respects_cooldown(tmp_path) -> None:
    state_path = tmp_path / "alert_dedup_state.json"
    line = "[2026-03-01T10:00:00] WARNING weekly pipeline: metrics-check reported threshold violations"

    first_now = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
    first = should_emit_and_update_state(state_path=state_path, line=line, cooldown_sec=600, now=first_now)
    second = should_emit_and_update_state(
        state_path=state_path,
        line=line,
        cooldown_sec=600,
        now=first_now + timedelta(seconds=120),
    )
    third = should_emit_and_update_state(
        state_path=state_path,
        line=line,
        cooldown_sec=600,
        now=first_now + timedelta(seconds=601),
    )

    assert first["send"] is True
    assert second["send"] is False
    assert third["send"] is True


def test_summarize_alert_dedup_state_reports_entry_and_timestamps(tmp_path) -> None:
    state_path = tmp_path / "alert_dedup_state.json"
    save_alert_dedup_state(
        state_path,
        {
            "sig_a": "2026-03-01T10:00:00Z",
            "sig_b": "2026-03-01T10:05:00Z",
        },
    )

    summary = summarize_alert_dedup_state(state_path, top_n=1, signature_preview_length=5)

    assert summary["entry_count"] == 2
    assert summary["oldest_timestamp"] == "2026-03-01T10:00:00Z"
    assert summary["newest_timestamp"] == "2026-03-01T10:05:00Z"
    assert len(summary["top_signatures"]) == 1
    assert summary["top_signatures"][0]["signature"] == "sig_b"
    assert summary["top_signatures"][0]["signature_preview"] == "sig_b"


def test_reset_alert_dedup_state_clears_state_with_backup(tmp_path) -> None:
    state_path = tmp_path / "alert_dedup_state.json"
    save_alert_dedup_state(state_path, {"sig_a": "2026-03-01T10:00:00Z"})

    result = reset_alert_dedup_state(state_path, backup=True)

    assert result["existed"] is True
    assert result["entry_count_before"] == 1
    assert result["entry_count_after"] == 0
    assert result["backup_path"]
    assert load_alert_dedup_state(state_path) == {}
    assert load_alert_dedup_state(result["backup_path"]) == {"sig_a": "2026-03-01T10:00:00Z"}


def test_get_alert_dedup_ttl_sec_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ALERT_DEDUP_TTL_SEC", "120")
    assert get_alert_dedup_ttl_sec() == 120


def test_get_alert_dedup_ttl_sec_fallback_on_invalid(monkeypatch) -> None:
    monkeypatch.setenv("ALERT_DEDUP_TTL_SEC", "invalid")
    assert get_alert_dedup_ttl_sec() == 604800


def test_should_emit_and_update_state_prunes_expired_entries(tmp_path, monkeypatch) -> None:
    state_path = tmp_path / "alert_dedup_state.json"
    now = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
    line = "[2026-03-01T10:00:00] WARNING weekly pipeline: metrics-check reported threshold violations"
    signature = build_alert_signature(line)

    save_alert_dedup_state(
        state_path,
        {
            "old_sig": "2026-03-01T09:58:00Z",
            signature: "2026-03-01T09:59:55Z",
        },
    )
    monkeypatch.setenv("ALERT_DEDUP_TTL_SEC", "30")

    result = should_emit_and_update_state(state_path=state_path, line=line, cooldown_sec=600, now=now)
    state = load_alert_dedup_state(state_path)

    assert result["send"] is False
    assert result["pruned_count"] == 1
    assert "old_sig" not in state
    assert signature in state


def test_summarize_alert_dedup_state_prunes_expired_entries(tmp_path, monkeypatch) -> None:
    state_path = tmp_path / "alert_dedup_state.json"
    now = datetime.now(timezone.utc)
    save_alert_dedup_state(
        state_path,
        {
            "old_sig": (now - timedelta(seconds=120)).isoformat().replace("+00:00", "Z"),
            "new_sig": (now - timedelta(seconds=10)).isoformat().replace("+00:00", "Z"),
        },
    )
    monkeypatch.setenv("ALERT_DEDUP_TTL_SEC", "20")

    summary = summarize_alert_dedup_state(state_path)
    state = load_alert_dedup_state(state_path)

    assert summary["pruned_count"] == 1
    assert summary["entry_count"] == 1
    assert "old_sig" not in state
    assert "new_sig" in state


def test_prune_alert_dedup_state_reports_removed_count(tmp_path) -> None:
    state_path = tmp_path / "alert_dedup_state.json"
    now = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
    save_alert_dedup_state(
        state_path,
        {
            "old_sig": "2026-03-01T09:58:00Z",
            "new_sig": "2026-03-01T09:59:50Z",
        },
    )

    result = prune_alert_dedup_state(state_path, ttl_sec=20, now=now)

    assert result["removed_count"] == 1
    assert result["entry_count_before"] == 2
    assert result["entry_count_after"] == 1

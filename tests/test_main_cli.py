import os
import sys
import json
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


def test_main_fetch_dispatch(monkeypatch, capsys):
    from src import main as main_module

    called = {"items": []}

    class DummyCollector:
        def collect(self, source, content):
            called["items"].append((source, content))

    monkeypatch.setattr(main_module, "DataCollector", DummyCollector)
    monkeypatch.setattr(
        main_module,
        "fetch_github_issues",
        lambda repo, state="open", limit=20: [{"source": "github:test/r", "content": "c"}],
    )
    monkeypatch.setattr(sys, "argv", ["prog", "fetch", "github", "test/r"])

    main_module.main()
    captured = capsys.readouterr()
    assert "Fetched and stored 1 entries." in captured.out
    assert called["items"] == [("github:test/r", "c")]


def test_main_doctor_dispatch(monkeypatch, capsys):
    from src import main as main_module

    monkeypatch.setattr(main_module, "print_doctor_report", lambda: print("Doctor report"))
    monkeypatch.setattr(sys, "argv", ["prog", "doctor"])

    main_module.main()
    captured = capsys.readouterr()
    assert "Doctor report" in captured.out


def test_main_doctor_json_dispatch(monkeypatch, capsys):
    from src import main as main_module

    monkeypatch.setattr(main_module, "print_doctor_report_json", lambda: print('{"ok": true}'))
    monkeypatch.setattr(sys, "argv", ["prog", "doctor", "--json"])

    main_module.main()
    captured = capsys.readouterr()
    assert '{"ok": true}' in captured.out


def test_main_env_init_dispatch(monkeypatch, capsys):
    from src import main as main_module

    monkeypatch.setattr(main_module, "ensure_env_from_example", lambda: {"created": 1, "added": 3, "missing_example": 0})
    monkeypatch.setattr(sys, "argv", ["prog", "env-init"])

    main_module.main()
    captured = capsys.readouterr()
    assert ".env initialized. created=1 added=3" in captured.out


def test_main_metrics_summary_dispatch(monkeypatch, capsys):
    from src import main as main_module

    called = {}

    def fake_handle(args):
        called["args"] = args
        print("metrics ok")

    monkeypatch.setattr(main_module, "handle_metrics_summary", fake_handle)
    monkeypatch.setattr(sys, "argv", ["prog", "metrics-summary", "--days", "7", "--json"])

    main_module.main()
    captured = capsys.readouterr()
    assert "metrics ok" in captured.out
    assert called["args"] == ["--days", "7", "--json"]


def test_main_metrics_check_dispatch(monkeypatch, capsys):
    from src import main as main_module

    called = {}

    def fake_handle(args):
        called["args"] = args
        print("check ok")
        return False

    monkeypatch.setattr(main_module, "handle_metrics_check", fake_handle)
    monkeypatch.setattr(sys, "argv", ["prog", "metrics-check", "--days", "14", "--json"])

    main_module.main()
    captured = capsys.readouterr()
    assert "check ok" in captured.out
    assert called["args"] == ["--days", "14", "--json"]


def test_main_metrics_check_exit_code_on_violation(monkeypatch):
    from src import main as main_module

    monkeypatch.setattr(main_module, "handle_metrics_check", lambda args: True)
    monkeypatch.setattr(sys, "argv", ["prog", "metrics-check"])

    with pytest.raises(SystemExit) as excinfo:
        main_module.main()

    assert excinfo.value.code == 1


def test_main_alert_dedup_status_dispatch(monkeypatch, capsys):
    from src import main as main_module

    called = {}

    def fake_handle(args):
        called["args"] = args
        print("dedup status ok")

    monkeypatch.setattr(main_module, "handle_alert_dedup_status", fake_handle)
    monkeypatch.setattr(sys, "argv", ["prog", "alert-dedup-status", "--json"])

    main_module.main()
    captured = capsys.readouterr()
    assert "dedup status ok" in captured.out
    assert called["args"] == ["--json"]


def test_main_alert_dedup_reset_dispatch(monkeypatch, capsys):
    from src import main as main_module

    called = {}

    def fake_handle(args):
        called["args"] = args
        print("dedup reset ok")

    monkeypatch.setattr(main_module, "handle_alert_dedup_reset", fake_handle)
    monkeypatch.setattr(sys, "argv", ["prog", "alert-dedup-reset", "--backup"])

    main_module.main()
    captured = capsys.readouterr()
    assert "dedup reset ok" in captured.out
    assert called["args"] == ["--backup"]


def test_main_alert_dedup_prune_dispatch(monkeypatch, capsys):
    from src import main as main_module

    called = {}

    def fake_handle(args):
        called["args"] = args
        print("dedup prune ok")

    monkeypatch.setattr(main_module, "handle_alert_dedup_prune", fake_handle)
    monkeypatch.setattr(sys, "argv", ["prog", "alert-dedup-prune", "--json"])

    main_module.main()
    captured = capsys.readouterr()
    assert "dedup prune ok" in captured.out
    assert called["args"] == ["--json"]


def test_handle_alert_dedup_status_json_output(monkeypatch, capsys):
    from src import main as main_module

    payload = {
        "state_path": "logs/alert_dedup_state.json",
        "exists": True,
        "entry_count": 2,
        "oldest_timestamp": "2026-03-01T10:00:00Z",
        "newest_timestamp": "2026-03-01T10:05:00Z",
        "top_signatures": [{"signature": "a", "signature_preview": "a", "timestamp": "2026-03-01T10:05:00Z"}],
    }
    monkeypatch.setattr(main_module, "summarize_alert_dedup_state", lambda path, top_n=5: payload)

    main_module.handle_alert_dedup_status(["--json"])
    captured = capsys.readouterr()
    assert json.loads(captured.out) == payload


def test_handle_alert_dedup_reset_text_output(monkeypatch, capsys):
    from src import main as main_module

    monkeypatch.setattr(
        main_module,
        "reset_alert_dedup_state",
        lambda path, backup=False: {
            "state_path": str(path),
            "existed": True,
            "entry_count_before": 3,
            "entry_count_after": 0,
            "backup_path": "",
        },
    )

    main_module.handle_alert_dedup_reset([])
    captured = capsys.readouterr()
    assert "Alert dedup state reset completed." in captured.out
    assert "Entries before: 3" in captured.out


def test_handle_alert_dedup_prune_text_output(monkeypatch, capsys):
    from src import main as main_module

    monkeypatch.setattr(
        main_module,
        "prune_alert_dedup_state",
        lambda path, ttl_sec=None: {
            "state_path": str(path),
            "ttl_sec": 600,
            "entry_count_before": 3,
            "entry_count_after": 1,
            "removed_count": 2,
        },
    )

    main_module.handle_alert_dedup_prune([])
    captured = capsys.readouterr()
    assert "Alert dedup prune completed." in captured.out
    assert "Removed: 2" in captured.out


def test_handle_metrics_check_json_includes_threshold_profile(monkeypatch, capsys):
    from src import main as main_module

    monkeypatch.setattr(
        main_module,
        "check_metric_thresholds",
        lambda days=30: {
            "threshold_profile": "stg",
            "violations": [],
            "continuous_alert": {
                "limit": 3,
                "warning_limit": 3,
                "critical_limit": 5,
                "severity": "none",
                "active": False,
                "violated_pipelines": [],
            },
        },
    )

    has_violations = main_module.handle_metrics_check(["--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert has_violations is False
    assert payload["threshold_profile"] == "stg"
    assert payload["continuous_alert"]["severity"] == "none"


def test_handle_metrics_check_text_includes_threshold_profile(monkeypatch, capsys):
    from src import main as main_module

    monkeypatch.setattr(
        main_module,
        "check_metric_thresholds",
        lambda days=30: {
            "threshold_profile": "dev",
            "violations": [],
            "continuous_alert": {
                "limit": 3,
                "warning_limit": 3,
                "critical_limit": 5,
                "severity": "warning",
                "active": True,
                "violated_pipelines": [
                    {
                        "pipeline": "weekly",
                        "consecutive_failures": 3,
                        "latest_run": "2026-03-01T00:00:00",
                        "severity": "warning",
                    }
                ],
            },
        },
    )

    has_violations = main_module.handle_metrics_check([])
    captured = capsys.readouterr()

    assert has_violations is False
    assert "Metric threshold profile: dev" in captured.out
    assert "Continuous SLO alert severity: warning" in captured.out


def test_handle_metrics_check_returns_true_on_critical_continuous_alert(monkeypatch, capsys):
    from src import main as main_module

    monkeypatch.setattr(
        main_module,
        "check_metric_thresholds",
        lambda days=30: {
            "threshold_profile": "prod",
            "violations": [],
            "continuous_alert": {
                "limit": 3,
                "warning_limit": 3,
                "critical_limit": 5,
                "severity": "critical",
                "active": True,
                "violated_pipelines": [
                    {
                        "pipeline": "daily",
                        "consecutive_failures": 5,
                        "latest_run": "2026-03-01T00:00:00",
                        "severity": "critical",
                    }
                ],
            },
        },
    )

    has_violations = main_module.handle_metrics_check([])

    assert has_violations is True


def test_main_ops_report_dispatch(monkeypatch, capsys):
    from src import main as main_module

    called = {}

    def fake_handle(args):
        called["args"] = args
        print("ops report ok")

    monkeypatch.setattr(main_module, "handle_ops_report", fake_handle)
    monkeypatch.setattr(sys, "argv", ["prog", "ops-report", "--days", "7"])

    main_module.main()
    captured = capsys.readouterr()
    assert "ops report ok" in captured.out
    assert called["args"] == ["--days", "7"]


def test_handle_ops_report_json_mode_outputs_json(monkeypatch, capsys):
    from src import main as main_module

    called = {}
    payload = {
        "generated_at": "2026-03-01T12:34:56",
        "days": 7,
        "window_start": "2026-02-23T12:34:56",
        "total_runs": 2,
        "health_score": 88,
        "health_breakdown": {
            "factors": {
                "average_pipeline_success_rate": 0.9,
                "violation_count": 1,
                "command_failures": 1,
                "alert_count": 2,
            },
            "penalties": {
                "success_rate": 6.0,
                "violations": 5.0,
                "command_failures": 2.0,
                "alerts": 0.4,
            },
            "formula": "score = ...",
        },
        "pipeline_success_rates": {},
        "threshold_violations_count": 0,
        "threshold_violations_by_pipeline": {},
        "top_alert_types": [],
        "recent_command_failures": 0,
    }

    def fake_generate_and_write_ops_report(days=7):
        called["days"] = days
        return payload, "docs/ops_reports/latest_ops_report.md"

    monkeypatch.setattr(main_module, "generate_and_write_ops_report", fake_generate_and_write_ops_report)
    monkeypatch.setattr(main_module, "append_activity", lambda *_args, **_kwargs: None)

    main_module.handle_ops_report(["--days", "7", "--json"])
    captured = capsys.readouterr()

    assert called["days"] == 7
    assert "Updated:" not in captured.out
    assert json.loads(captured.out) == payload


def test_handle_metrics_summary_json_includes_health_fields(monkeypatch, capsys):
    from src import main as main_module

    payload = {
        "days": 7,
        "window_start": "2026-02-23T12:34:56",
        "total_runs": 2,
        "pipelines": {},
        "totals": {"command_failures": 1, "alert_count": 2},
        "health_score": 91,
        "health_breakdown": {
            "factors": {
                "average_pipeline_success_rate": 0.95,
                "violation_count": 1,
                "command_failures": 1,
                "alert_count": 2,
            },
            "penalties": {
                "success_rate": 3.0,
                "violations": 5.0,
                "command_failures": 2.0,
                "alerts": 0.4,
            },
            "formula": "score = ...",
        },
    }
    monkeypatch.setattr(main_module, "build_metrics_summary", lambda days=30: payload)

    main_module.handle_metrics_summary(["--days", "7", "--json"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert data["health_score"] == 91
    assert data["health_breakdown"]["factors"]["violation_count"] == 1


def test_handle_metrics_summary_text_includes_health_fields(monkeypatch, capsys):
    from src import main as main_module

    payload = {
        "days": 7,
        "window_start": "2026-02-23T12:34:56",
        "total_runs": 2,
        "pipelines": {},
        "totals": {"command_failures": 1, "alert_count": 2},
        "health_score": 91,
        "health_breakdown": {
            "factors": {
                "average_pipeline_success_rate": 0.95,
                "violation_count": 1,
                "command_failures": 1,
                "alert_count": 2,
            },
            "penalties": {
                "success_rate": 3.0,
                "violations": 5.0,
                "command_failures": 2.0,
                "alerts": 0.4,
            },
            "formula": "score = ...",
        },
    }
    monkeypatch.setattr(main_module, "build_metrics_summary", lambda days=30: payload)

    main_module.handle_metrics_summary(["--days", "7"])
    captured = capsys.readouterr()

    assert "health_score: 91" in captured.out
    assert "health_breakdown:" in captured.out


def test_main_apply_insights_dispatch(monkeypatch, capsys, tmp_path):
    from src import main as main_module

    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(main_module, "load_entries", lambda: [{"source": "s", "content": "c"}])
    monkeypatch.setattr(main_module, "summarize_by_source", lambda e: {"s": 1})
    monkeypatch.setattr(main_module, "write_backlog", lambda summary, ai_summary="", **kwargs: "docs/improvement_backlog.md")
    monkeypatch.setattr(main_module, "update_instruction_file", lambda top_sources: ".github/instructions/common.instructions.md")
    monkeypatch.setattr(sys, "argv", ["prog", "apply-insights"])

    main_module.main()
    captured = capsys.readouterr()
    assert "Updated: docs/improvement_backlog.md" in captured.out
    assert "Synced Spotlight actions:" in captured.out
    assert "Synced Promoted actions:" in captured.out
    assert "Warning: promoted actions below threshold (0 < 1)." in captured.out


def test_main_apply_insights_transfers_spotlight_actions(monkeypatch, tmp_path):
    from src import main as main_module

    monkeypatch.chdir(tmp_path)
    weekly_dir = tmp_path / "docs" / "weekly_reports"
    weekly_dir.mkdir(parents=True, exist_ok=True)
    (weekly_dir / "latest_weekly_report.md").write_text("dummy", encoding="utf-8")

    monkeypatch.setattr(main_module, "load_entries", lambda: [{"source": "s", "content": "c"}])
    monkeypatch.setattr(main_module, "summarize_by_source", lambda e: {"s": 1})
    monkeypatch.setattr(
        main_module,
        "extract_spotlight_action_items_from_markdown",
        lambda md: [
            {"action": "Do X", "priority": "High"},
            {"action": "Do Y", "priority": "Low"},
        ],
    )
    monkeypatch.setattr(main_module, "extract_promoted_actions_from_markdown", lambda md: ["Do X"])

    captured = {}

    def fake_write_backlog(summary, ai_summary="", spotlight_actions=None, promoted_actions=None, **kwargs):
        captured["spotlight_actions"] = spotlight_actions
        captured["promoted_actions"] = promoted_actions
        return "docs/improvement_backlog.md"

    monkeypatch.setattr(main_module, "write_backlog", fake_write_backlog)
    monkeypatch.setattr(main_module, "update_instruction_file", lambda top_sources: ".github/instructions/common.instructions.md")

    main_module.handle_apply_insights([])
    assert captured["spotlight_actions"] == ["[High] Do X", "[Low] Do Y"]
    assert captured["promoted_actions"] == ["Do X"]


def test_main_apply_insights_sync_issues_enabled(monkeypatch, tmp_path, capsys):
    from src import main as main_module

    monkeypatch.chdir(tmp_path)
    weekly_dir = tmp_path / "docs" / "weekly_reports"
    weekly_dir.mkdir(parents=True, exist_ok=True)
    (weekly_dir / "latest_weekly_report.md").write_text(
        "# Weekly Report (2026-W09)\n\n## Action Items\n- [ ] [Promoted] Do X\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("AUTO_SYNC_PROMOTED_ISSUES", "1")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(main_module, "load_entries", lambda: [{"source": "s", "content": "c"}])
    monkeypatch.setattr(main_module, "summarize_by_source", lambda e: {"s": 1})
    monkeypatch.setattr(main_module, "extract_spotlight_action_items_from_markdown", lambda md: [])
    monkeypatch.setattr(main_module, "extract_promoted_actions_from_markdown", lambda md: ["Do X"])
    monkeypatch.setattr(main_module, "write_backlog", lambda summary, ai_summary="", **kwargs: "docs/improvement_backlog.md")
    monkeypatch.setattr(main_module, "update_instruction_file", lambda top_sources: ".github/instructions/common.instructions.md")
    captured_sync = {}

    def fake_sync(
        actions,
        repo,
        token,
        labels=None,
        assignees=None,
        period_key=None,
        source_period_type=None,
        include_period_label=False,
    ):
        captured_sync["period_key"] = period_key
        captured_sync["source_period_type"] = source_period_type
        captured_sync["include_period_label"] = include_period_label
        return {"created": 1, "skipped_existing": 0}

    monkeypatch.setattr(
        main_module,
        "sync_promoted_actions_to_github_issues",
        fake_sync,
    )

    main_module.handle_apply_insights([])
    captured = capsys.readouterr()
    assert "Issue sync: created=1 skipped_existing=0" in captured.out
    assert captured_sync["period_key"] == "2026-W09"
    assert captured_sync["source_period_type"] == "weekly"
    assert captured_sync["include_period_label"] is False


def test_main_apply_insights_sync_issues_enabled_without_week_label(monkeypatch, tmp_path):
    from src import main as main_module

    monkeypatch.chdir(tmp_path)
    weekly_dir = tmp_path / "docs" / "weekly_reports"
    weekly_dir.mkdir(parents=True, exist_ok=True)
    (weekly_dir / "latest_weekly_report.md").write_text("## Action Items\n- [ ] [Promoted] Do X\n", encoding="utf-8")

    monkeypatch.setenv("AUTO_SYNC_PROMOTED_ISSUES", "1")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(main_module, "load_entries", lambda: [{"source": "s", "content": "c"}])
    monkeypatch.setattr(main_module, "summarize_by_source", lambda e: {"s": 1})
    monkeypatch.setattr(main_module, "extract_spotlight_action_items_from_markdown", lambda md: [])
    monkeypatch.setattr(main_module, "extract_promoted_actions_from_markdown", lambda md: ["Do X"])
    monkeypatch.setattr(main_module, "write_backlog", lambda summary, ai_summary="", **kwargs: "docs/improvement_backlog.md")
    monkeypatch.setattr(main_module, "update_instruction_file", lambda top_sources: ".github/instructions/common.instructions.md")

    captured_sync = {}

    def fake_sync(
        actions,
        repo,
        token,
        labels=None,
        assignees=None,
        period_key=None,
        source_period_type=None,
        include_period_label=False,
    ):
        captured_sync["period_key"] = period_key
        captured_sync["source_period_type"] = source_period_type
        captured_sync["include_period_label"] = include_period_label
        return {"created": 1, "skipped_existing": 0}

    monkeypatch.setattr(main_module, "sync_promoted_actions_to_github_issues", fake_sync)

    main_module.handle_apply_insights([])
    assert captured_sync["period_key"] == ""
    assert captured_sync["source_period_type"] == "weekly"
    assert captured_sync["include_period_label"] is False


def test_main_apply_insights_sync_issues_enabled_with_monthly_promoted_period_key(monkeypatch, tmp_path, capsys):
    from src import main as main_module

    monkeypatch.chdir(tmp_path)

    monthly_dir = tmp_path / "docs" / "monthly_reports"
    monthly_dir.mkdir(parents=True, exist_ok=True)
    (monthly_dir / "latest_monthly_report.md").write_text(
        "# Monthly Report (2026-02)\n\n"
        "## Promotable Actions\n"
        "- [ ] [Promoted] Do monthly X\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("AUTO_SYNC_PROMOTED_ISSUES", "1")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(main_module, "load_entries", lambda: [{"source": "s", "content": "c"}])
    monkeypatch.setattr(main_module, "summarize_by_source", lambda e: {"s": 1})
    monkeypatch.setattr(main_module, "write_backlog", lambda summary, ai_summary="", **kwargs: "docs/improvement_backlog.md")
    monkeypatch.setattr(main_module, "update_instruction_file", lambda top_sources: ".github/instructions/common.instructions.md")

    captured_sync_calls: list[dict[str, str | list[str]]] = []

    def fake_sync(
        actions,
        repo,
        token,
        labels=None,
        assignees=None,
        period_key=None,
        source_period_type=None,
        include_period_label=False,
    ):
        captured_sync_calls.append(
            {
                "actions": actions,
                "period_key": period_key,
                "source_period_type": source_period_type,
                "include_period_label": include_period_label,
            }
        )
        return {"created": 1, "skipped_existing": 0}

    monkeypatch.setattr(main_module, "sync_promoted_actions_to_github_issues", fake_sync)

    main_module.handle_apply_insights([])
    captured = capsys.readouterr()
    assert "Synced Monthly Promoted actions: 1" in captured.out
    assert captured_sync_calls == [
        {
            "actions": ["Do monthly X"],
            "period_key": "2026-02",
            "source_period_type": "monthly",
            "include_period_label": False,
        }
    ]


def test_main_apply_insights_sync_issues_with_period_labels_enabled(monkeypatch, tmp_path):
    from src import main as main_module

    monkeypatch.chdir(tmp_path)
    weekly_dir = tmp_path / "docs" / "weekly_reports"
    weekly_dir.mkdir(parents=True, exist_ok=True)
    (weekly_dir / "latest_weekly_report.md").write_text(
        "# Weekly Report (2026-W09)\n\n## Action Items\n- [ ] [Promoted] Do X\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("AUTO_SYNC_PROMOTED_ISSUES", "1")
    monkeypatch.setenv("GITHUB_ISSUE_PERIOD_LABELS", "1")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_ISSUE_LABELS", "starter,auto")
    monkeypatch.setattr(main_module, "load_entries", lambda: [{"source": "s", "content": "c"}])
    monkeypatch.setattr(main_module, "summarize_by_source", lambda e: {"s": 1})
    monkeypatch.setattr(main_module, "extract_spotlight_action_items_from_markdown", lambda md: [])
    monkeypatch.setattr(main_module, "extract_promoted_actions_from_markdown", lambda md: ["Do X"])
    monkeypatch.setattr(main_module, "write_backlog", lambda summary, ai_summary="", **kwargs: "docs/improvement_backlog.md")
    monkeypatch.setattr(main_module, "update_instruction_file", lambda top_sources: ".github/instructions/common.instructions.md")

    captured_sync = {}

    def fake_sync(
        actions,
        repo,
        token,
        labels=None,
        assignees=None,
        period_key=None,
        source_period_type=None,
        include_period_label=False,
    ):
        captured_sync["labels"] = labels
        captured_sync["source_period_type"] = source_period_type
        captured_sync["include_period_label"] = include_period_label
        return {"created": 1, "skipped_existing": 0}

    monkeypatch.setattr(main_module, "sync_promoted_actions_to_github_issues", fake_sync)

    main_module.handle_apply_insights([])
    assert captured_sync["labels"] == ["starter", "auto"]
    assert captured_sync["source_period_type"] == "weekly"
    assert captured_sync["include_period_label"] is True


def test_main_apply_insights_sync_issues_routes_assignees_by_rules(monkeypatch, tmp_path):
    from src import main as main_module

    monkeypatch.chdir(tmp_path)
    weekly_dir = tmp_path / "docs" / "weekly_reports"
    monthly_dir = tmp_path / "docs" / "monthly_reports"
    weekly_dir.mkdir(parents=True, exist_ok=True)
    monthly_dir.mkdir(parents=True, exist_ok=True)
    (weekly_dir / "latest_weekly_report.md").write_text(
        "# Weekly Report (2026-W09)\n\n## Action Items\n- [ ] [Promoted] Do weekly\n",
        encoding="utf-8",
    )
    (monthly_dir / "latest_monthly_report.md").write_text(
        "# Monthly Report (2026-02)\n\n## Promotable Actions\n- [ ] [Promoted] Do monthly\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("AUTO_SYNC_PROMOTED_ISSUES", "1")
    monkeypatch.setenv("GITHUB_ISSUE_PERIOD_LABELS", "1")
    monkeypatch.setenv("GITHUB_ISSUE_LABELS", "starter")
    monkeypatch.setenv("GITHUB_ISSUE_ASSIGNEE_RULES", "ai-starter-weekly:alice;ai-starter-monthly:bob;default:teamlead")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(main_module, "load_entries", lambda: [{"source": "s", "content": "c"}])
    monkeypatch.setattr(main_module, "summarize_by_source", lambda e: {"s": 1})
    monkeypatch.setattr(main_module, "extract_spotlight_action_items_from_markdown", lambda md: [])
    monkeypatch.setattr(main_module, "extract_promoted_actions_from_markdown", lambda md: ["Do weekly"])
    monkeypatch.setattr(main_module, "extract_monthly_promoted_actions_from_markdown", lambda md: ["Do monthly"])
    monkeypatch.setattr(main_module, "write_backlog", lambda summary, ai_summary="", **kwargs: "docs/improvement_backlog.md")
    monkeypatch.setattr(main_module, "update_instruction_file", lambda top_sources: ".github/instructions/common.instructions.md")

    captured_sync_calls: list[dict[str, str | list[str] | None]] = []

    def fake_sync(
        actions,
        repo,
        token,
        labels=None,
        assignees=None,
        period_key=None,
        source_period_type=None,
        include_period_label=False,
    ):
        captured_sync_calls.append(
            {
                "source_period_type": source_period_type,
                "assignees": assignees,
            }
        )
        return {"created": 1, "skipped_existing": 0}

    monkeypatch.setattr(main_module, "sync_promoted_actions_to_github_issues", fake_sync)

    main_module.handle_apply_insights([])
    assert captured_sync_calls == [
        {"source_period_type": "weekly", "assignees": ["alice"]},
        {"source_period_type": "monthly", "assignees": ["bob"]},
    ]


def test_main_apply_insights_sync_issues_explicit_assignees_override_rules(monkeypatch, tmp_path):
    from src import main as main_module

    monkeypatch.chdir(tmp_path)
    weekly_dir = tmp_path / "docs" / "weekly_reports"
    weekly_dir.mkdir(parents=True, exist_ok=True)
    (weekly_dir / "latest_weekly_report.md").write_text(
        "# Weekly Report (2026-W09)\n\n## Action Items\n- [ ] [Promoted] Do weekly\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("AUTO_SYNC_PROMOTED_ISSUES", "1")
    monkeypatch.setenv("GITHUB_ISSUE_PERIOD_LABELS", "1")
    monkeypatch.setenv("GITHUB_ISSUE_ASSIGNEES", "octocat")
    monkeypatch.setenv("GITHUB_ISSUE_ASSIGNEE_RULES", "ai-starter-weekly:alice;default:teamlead")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(main_module, "load_entries", lambda: [{"source": "s", "content": "c"}])
    monkeypatch.setattr(main_module, "summarize_by_source", lambda e: {"s": 1})
    monkeypatch.setattr(main_module, "extract_spotlight_action_items_from_markdown", lambda md: [])
    monkeypatch.setattr(main_module, "extract_promoted_actions_from_markdown", lambda md: ["Do weekly"])
    monkeypatch.setattr(main_module, "write_backlog", lambda summary, ai_summary="", **kwargs: "docs/improvement_backlog.md")
    monkeypatch.setattr(main_module, "update_instruction_file", lambda top_sources: ".github/instructions/common.instructions.md")

    captured_sync = {}

    def fake_sync(
        actions,
        repo,
        token,
        labels=None,
        assignees=None,
        period_key=None,
        source_period_type=None,
        include_period_label=False,
    ):
        captured_sync["assignees"] = assignees
        return {"created": 1, "skipped_existing": 0}

    monkeypatch.setattr(main_module, "sync_promoted_actions_to_github_issues", fake_sync)

    main_module.handle_apply_insights([])
    assert captured_sync["assignees"] == ["octocat"]


def test_main_apply_insights_sync_issues_skips_on_invalid_assignee_rules(monkeypatch, tmp_path, capsys):
    from src import main as main_module

    monkeypatch.chdir(tmp_path)
    weekly_dir = tmp_path / "docs" / "weekly_reports"
    weekly_dir.mkdir(parents=True, exist_ok=True)
    (weekly_dir / "latest_weekly_report.md").write_text(
        "# Weekly Report (2026-W09)\n\n## Action Items\n- [ ] [Promoted] Do weekly\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("AUTO_SYNC_PROMOTED_ISSUES", "1")
    monkeypatch.setenv("GITHUB_ISSUE_ASSIGNEE_RULES", "broken")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(main_module, "load_entries", lambda: [{"source": "s", "content": "c"}])
    monkeypatch.setattr(main_module, "summarize_by_source", lambda e: {"s": 1})
    monkeypatch.setattr(main_module, "extract_spotlight_action_items_from_markdown", lambda md: [])
    monkeypatch.setattr(main_module, "extract_promoted_actions_from_markdown", lambda md: ["Do weekly"])
    monkeypatch.setattr(main_module, "write_backlog", lambda summary, ai_summary="", **kwargs: "docs/improvement_backlog.md")
    monkeypatch.setattr(main_module, "update_instruction_file", lambda top_sources: ".github/instructions/common.instructions.md")

    called = {"sync": 0}

    def fake_sync(*args, **kwargs):
        called["sync"] += 1
        return {"created": 1, "skipped_existing": 0}

    monkeypatch.setattr(main_module, "sync_promoted_actions_to_github_issues", fake_sync)

    main_module.handle_apply_insights([])
    captured = capsys.readouterr()
    assert "Issue sync skipped: invalid GITHUB_ISSUE_ASSIGNEE_RULES" in captured.out
    assert called["sync"] == 0


def test_main_apply_insights_dry_run(monkeypatch, tmp_path, capsys):
    from src import main as main_module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main_module, "load_entries", lambda: [{"source": "s", "content": "c"}])
    monkeypatch.setattr(main_module, "summarize_by_source", lambda e: {"s": 1})
    monkeypatch.setattr(main_module, "extract_spotlight_action_items_from_markdown", lambda md: [])
    monkeypatch.setattr(main_module, "extract_promoted_actions_from_markdown", lambda md: [])

    called = {"write": 0, "update": 0}
    monkeypatch.setattr(main_module, "write_backlog", lambda *args, **kwargs: called.__setitem__("write", called["write"] + 1))
    monkeypatch.setattr(main_module, "update_instruction_file", lambda *args, **kwargs: called.__setitem__("update", called["update"] + 1))

    main_module.handle_apply_insights(["--dry-run"])
    captured = capsys.readouterr()
    assert "Dry-run: no files were written." in captured.out
    assert called["write"] == 0
    assert called["update"] == 0


def test_main_analyze_ai_fallback_without_api_key(monkeypatch, capsys):
    from src import main as main_module

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(main_module, "load_entries", lambda: [{"source": "s", "content": "need docs"}])
    monkeypatch.setattr(main_module, "summarize_by_source", lambda e: {"s": 1})
    monkeypatch.setattr(main_module, "generate_fallback_summary", lambda e: "fallback generated")
    monkeypatch.setattr(sys, "argv", ["prog", "analyze", "--ai"])

    main_module.main()
    captured = capsys.readouterr()
    assert "Using local fallback summary" in captured.out
    assert "fallback generated" in captured.out


def test_main_analyze_ai_fallback_on_api_error(monkeypatch, capsys):
    from src import main as main_module

    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setattr(main_module, "load_entries", lambda: [{"source": "s", "content": "need docs"}])
    monkeypatch.setattr(main_module, "summarize_by_source", lambda e: {"s": 1})

    def raise_error(entries, api_key, model="gpt-4o-mini"):
        raise RuntimeError("quota")

    monkeypatch.setattr(main_module, "generate_ai_summary", raise_error)
    monkeypatch.setattr(main_module, "generate_fallback_summary", lambda e: "fallback generated")
    monkeypatch.setattr(sys, "argv", ["prog", "analyze", "--ai"])

    main_module.main()
    captured = capsys.readouterr()
    assert "AI API error" in captured.out
    assert "fallback generated" in captured.out


def test_main_weekly_report_dispatch(monkeypatch, capsys):
    from src import main as main_module

    monkeypatch.setattr(main_module, "load_entries", lambda: [{"source": "s", "content": "c", "collected_at": "2026-02-28T12:00:00"}])
    monkeypatch.setattr(main_module, "summarize_by_source", lambda e: {"s": 1})
    monkeypatch.setattr(main_module, "filter_entries_by_days", lambda entries, days: entries)
    monkeypatch.setattr(main_module, "write_weekly_report", lambda entries, summary, ai_summary="", **kwargs: "docs/weekly_reports/weekly-report-2026-W09.md")
    monkeypatch.setattr(sys, "argv", ["prog", "weekly-report", "--days", "7"])

    main_module.main()
    captured = capsys.readouterr()
    assert "Updated: docs/weekly_reports/weekly-report-2026-W09.md" in captured.out


def test_main_monthly_report_dispatch(monkeypatch, capsys):
    from src import main as main_module

    calls = {"filters": [], "previous_summary": None}

    def fake_filter(entries, start_inclusive, end_exclusive, include_missing_timestamp=False):
        calls["filters"].append(include_missing_timestamp)
        if start_inclusive.strftime("%Y-%m") == "2026-02":
            return [{"source": "s", "content": "c", "collected_at": "2026-02-28T12:00:00"}]
        return [{"source": "prev", "content": "c", "collected_at": "2026-01-28T12:00:00"}]

    monkeypatch.setattr(main_module, "load_entries", lambda: [{"source": "s", "content": "c", "collected_at": "2026-02-28T12:00:00"}])
    monkeypatch.setattr(main_module, "filter_entries_between", fake_filter)

    def fake_summary(entries):
        if entries and entries[0].get("source") == "prev":
            return {"prev": 1}
        return {"s": 1}

    monkeypatch.setattr(main_module, "summarize_by_source", fake_summary)

    def fake_write_monthly_report(entries, summary, ai_summary="", month_label=None, previous_summary=None, **kwargs):
        calls["previous_summary"] = previous_summary
        return f"docs/monthly_reports/monthly-report-{month_label}.md"

    monkeypatch.setattr(
        main_module,
        "write_monthly_report",
        fake_write_monthly_report,
    )
    monkeypatch.setattr(sys, "argv", ["prog", "monthly-report", "--month", "2026-02"])

    main_module.main()
    captured = capsys.readouterr()
    assert calls["filters"] == [False, False]
    assert calls["previous_summary"] == {"prev": 1}
    assert "Updated: docs/monthly_reports/monthly-report-2026-02.md" in captured.out


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


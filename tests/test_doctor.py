from src import doctor
import json


def test_run_doctor_reports_errors_for_invalid_values(monkeypatch):
    monkeypatch.setenv("PROMOTED_MIN_COUNT", "abc")
    monkeypatch.setenv("CONNECTOR_RETRIES", "0")
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "invalid")

    result = doctor.run_doctor()
    assert "PROMOTED_MIN_COUNT must be an integer" in result["errors"]
    assert "CONNECTOR_RETRIES must be >= 1" in result["errors"]
    assert "ALERT_WEBHOOK_URL must start with http:// or https://" in result["errors"]


def test_run_doctor_requires_github_settings_when_issue_sync_enabled(monkeypatch):
    monkeypatch.setenv("AUTO_SYNC_PROMOTED_ISSUES", "1")
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    result = doctor.run_doctor()
    assert "GITHUB_REPO is required when AUTO_SYNC_PROMOTED_ISSUES is enabled" in result["errors"]
    assert "GITHUB_TOKEN is required when AUTO_SYNC_PROMOTED_ISSUES is enabled" in result["errors"]


def test_doctor_json_ok_with_warnings_when_fail_on_warnings_unset(monkeypatch, capsys):
    monkeypatch.delenv("DOCTOR_FAIL_ON_WARNINGS", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("PROMOTED_MIN_COUNT", "1")
    monkeypatch.setenv("ALERTS_MAX_LINES", "500")
    monkeypatch.setenv("CONNECTOR_RETRIES", "3")
    monkeypatch.setenv("CONNECTOR_BACKOFF_SEC", "0.5")
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("AUTO_SYNC_PROMOTED_ISSUES", "0")

    doctor.print_doctor_report_json()
    payload = json.loads(capsys.readouterr().out)

    assert payload["errors"] == []
    assert len(payload["warnings"]) >= 1
    assert payload["fail_on_warnings"] is False
    assert payload["ok"] is True


def test_doctor_json_not_ok_with_warnings_when_fail_on_warnings_enabled(monkeypatch, capsys):
    monkeypatch.setenv("DOCTOR_FAIL_ON_WARNINGS", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("PROMOTED_MIN_COUNT", "1")
    monkeypatch.setenv("ALERTS_MAX_LINES", "500")
    monkeypatch.setenv("CONNECTOR_RETRIES", "3")
    monkeypatch.setenv("CONNECTOR_BACKOFF_SEC", "0.5")
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("AUTO_SYNC_PROMOTED_ISSUES", "0")

    doctor.print_doctor_report_json()
    payload = json.loads(capsys.readouterr().out)

    assert payload["errors"] == []
    assert len(payload["warnings"]) >= 1
    assert payload["fail_on_warnings"] is True
    assert payload["ok"] is False


def test_run_doctor_reports_errors_for_invalid_pipeline_common_parameters(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_RETRIES", "0")
    monkeypatch.setenv("ALERT_WEBHOOK_BACKOFF_SEC", "0")
    monkeypatch.setenv("ALERT_DEDUP_COOLDOWN_SEC", "-1")
    monkeypatch.setenv("CONNECTOR_MAX_WAIT_SEC", "-0.5")

    result = doctor.run_doctor()

    assert "ALERT_WEBHOOK_RETRIES must be >= 1" in result["errors"]
    assert "ALERT_WEBHOOK_BACKOFF_SEC must be >= 0.1" in result["errors"]
    assert "ALERT_DEDUP_COOLDOWN_SEC must be >= 0" in result["errors"]
    assert "CONNECTOR_MAX_WAIT_SEC must be >= 0" in result["errors"]


def test_run_doctor_reports_warning_for_invalid_alert_webhook_format(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_FORMAT", "discord")

    result = doctor.run_doctor()

    assert "ALERT_WEBHOOK_FORMAT should be one of: generic, slack, teams" in result["warnings"]

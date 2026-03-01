from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "verify_weekly_ops_artifacts.py"
    spec = importlib.util.spec_from_file_location("verify_weekly_ops_artifacts", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_required_files_returns_empty_when_all_files_exist(tmp_path):
    module = _load_module()

    for relative_path in module.DEFAULT_REQUIRED_FILES:
        file_path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("ok", encoding="utf-8")

    missing = module.missing_required_files(list(module.DEFAULT_REQUIRED_FILES), tmp_path)

    assert missing == []


def test_missing_required_files_returns_only_missing_entries(tmp_path):
    module = _load_module()

    present = module.DEFAULT_REQUIRED_FILES[0]
    present_path = tmp_path / present
    present_path.parent.mkdir(parents=True, exist_ok=True)
    present_path.write_text("ok", encoding="utf-8")

    missing = module.missing_required_files(list(module.DEFAULT_REQUIRED_FILES), tmp_path)

    assert present not in missing
    assert set(missing) == set(module.DEFAULT_REQUIRED_FILES[1:])


def test_build_verification_report_contains_ok_missing_and_summary(tmp_path):
    module = _load_module()

    present = module.DEFAULT_REQUIRED_FILES[0]
    present_path = tmp_path / present
    present_path.parent.mkdir(parents=True, exist_ok=True)
    present_path.write_text("ok", encoding="utf-8")

    report = module.build_verification_report(list(module.DEFAULT_REQUIRED_FILES), tmp_path)

    checks = report.get("checks")
    assert isinstance(checks, list)
    assert len(checks) == len(module.DEFAULT_REQUIRED_FILES)
    status_by_path = {
        str(item.get("path")): str(item.get("status"))
        for item in checks
        if isinstance(item, dict)
    }
    assert status_by_path[present] == "OK"
    for missing_path in module.DEFAULT_REQUIRED_FILES[1:]:
        assert status_by_path[missing_path] == "MISSING"

    summary = report.get("summary")
    assert isinstance(summary, dict)
    assert summary == {
        "total": len(module.DEFAULT_REQUIRED_FILES),
        "ok": 1,
        "missing": len(module.DEFAULT_REQUIRED_FILES) - 1,
    }


def test_write_verification_json_writes_utf8_json_file(tmp_path):
    module = _load_module()

    report = {
        "root": str(tmp_path),
        "checks": [{"path": "docs/ops_reports/index.html", "status": "MISSING"}],
        "summary": {"total": 1, "ok": 0, "missing": 1},
    }
    output_path = tmp_path / "logs" / "weekly-artifact-verify.json"

    module.write_verification_json(report, output_path)

    assert output_path.exists()
    text = output_path.read_text(encoding="utf-8")
    assert '"status": "MISSING"' in text
    assert '"missing": 1' in text
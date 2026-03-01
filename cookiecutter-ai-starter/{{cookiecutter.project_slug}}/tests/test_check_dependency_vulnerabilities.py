from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "check_dependency_vulnerabilities.py"
    spec = importlib.util.spec_from_file_location("check_dependency_vulnerabilities", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_fail_level_fallbacks_to_default():
    module = _load_module()

    assert module.normalize_fail_level("critical") == "critical"
    assert module.normalize_fail_level("UNKNOWN") == "high"
    assert module.normalize_fail_level(None) == "high"


def test_collect_findings_and_fail_threshold():
    module = _load_module()

    payload = {
        "dependencies": [
            {
                "name": "demo",
                "version": "1.0.0",
                "vulns": [
                    {
                        "id": "GHSA-demo-1",
                        "severity": [{"score": "9.8"}],
                    },
                    {
                        "id": "GHSA-demo-2",
                        "severity": [{"score": "5.0"}],
                    },
                ],
            }
        ]
    }

    findings = module.collect_findings(payload)

    assert findings == [
        {"package": "demo", "version": "1.0.0", "id": "GHSA-demo-1", "severity": "critical"},
        {"package": "demo", "version": "1.0.0", "id": "GHSA-demo-2", "severity": "medium"},
    ]
    assert module.should_fail(findings, "high") is True
    assert module.should_fail(findings, "critical") is True
    assert module.should_fail(findings, "critical") is True


def test_vulnerability_severity_defaults_to_high_when_missing_severity():
    module = _load_module()

    severity = module.vulnerability_severity({"id": "GHSA-no-severity"})

    assert severity == "high"

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "compare_dependency_vuln_snapshots.py"
    spec = importlib.util.spec_from_file_location("compare_dependency_vuln_snapshots", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compare_snapshots_splits_new_and_resolved():
    module = _load_module()

    current = {
        "findings": [
            {"package": "a", "version": "1", "id": "GHSA-1", "severity": "high"},
            {"package": "b", "version": "1", "id": "GHSA-2", "severity": "medium"},
        ]
    }
    previous = {
        "findings": [
            {"package": "a", "version": "1", "id": "GHSA-1", "severity": "high"},
            {"package": "c", "version": "2", "id": "GHSA-3", "severity": "critical"},
        ]
    }

    result = module.compare_snapshots(current, previous)

    assert result["current_count"] == 2
    assert result["previous_count"] == 2
    assert result["newly_detected"] == [{"package": "b", "version": "1", "id": "GHSA-2", "severity": "medium"}]
    assert result["resolved"] == [{"package": "c", "version": "2", "id": "GHSA-3", "severity": "critical"}]

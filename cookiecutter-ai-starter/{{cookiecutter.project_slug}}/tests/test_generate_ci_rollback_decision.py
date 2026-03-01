from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "generate_ci_rollback_decision.py"
    spec = importlib.util.spec_from_file_location("generate_ci_rollback_decision", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_decision_recommends_rollback_for_test_failure():
    module = _load_module()

    result = module.build_decision({"run_tests": "failure", "doctor_check": "success"}, dependency_blockers=False)

    assert result["recommendation"] == "rollback-recommended"
    assert result["risk_level"] == "high"
    assert "run_tests" in result["failed_steps"]


def test_build_decision_blocks_release_for_dependency_gate():
    module = _load_module()

    result = module.build_decision({"dependency_scan": "failure"}, dependency_blockers=True)

    assert result["recommendation"] == "block-release-fix-dependencies"
    assert result["risk_level"] == "high"

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "scan_secrets.py"
    spec = importlib.util.spec_from_file_location("scan_secrets", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scan_paths_detects_secret_like_pattern(tmp_path):
    module = _load_module()

    secret_file = tmp_path / "sample.txt"
    secret_file.write_text("OPENAI_API_KEY=sk-1234567890123456789012345\n", encoding="utf-8")

    findings = module.scan_paths([secret_file], tmp_path)

    assert len(findings) == 1
    assert findings[0]["pattern"] == "openai_api_key"


def test_scan_paths_ignores_placeholder_values(tmp_path):
    module = _load_module()

    placeholder_file = tmp_path / "sample.txt"
    placeholder_file.write_text("OPENAI_API_KEY=sk-...\n", encoding="utf-8")

    findings = module.scan_paths([placeholder_file], tmp_path)

    assert findings == []

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "check_release_preconditions.py"
    spec = importlib.util.spec_from_file_location("check_release_preconditions", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validate_target_ref_consistency_accepts_matching_branch():
    module = _load_module()

    assert module.validate_target_ref_consistency("main", "main") is None
    assert module.validate_target_ref_consistency("refs/heads/main", "main") is None


def test_validate_target_ref_consistency_rejects_mismatch():
    module = _load_module()

    error = module.validate_target_ref_consistency("release", "main")

    assert isinstance(error, str)
    assert "mismatch" in error.lower()


def test_validate_notes_file_checks_existence(tmp_path: Path):
    module = _load_module()

    notes = tmp_path / "notes.md"
    assert module.validate_notes_file(notes) is not None

    notes.write_text("# notes\n", encoding="utf-8")
    assert module.validate_notes_file(notes) is None

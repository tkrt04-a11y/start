from __future__ import annotations

import pytest

from src.schema_validation import validate_schema_version_compatibility


def test_schema_version_compatibility_passes_when_major_matches() -> None:
    payload = {"schema_version": "1.1.0"}
    schema = {
        "type": "object",
        "properties": {
            "schema_version": {"type": "string", "const": "1.1.0"},
        },
    }

    validate_schema_version_compatibility(payload, schema, compatibility_level="major")


def test_schema_version_compatibility_fails_when_major_mismatches() -> None:
    payload = {"schema_version": "2.0.0"}
    schema = {
        "type": "object",
        "properties": {
            "schema_version": {"type": "string", "const": "1.1.0"},
        },
    }

    with pytest.raises(ValueError, match="major version mismatch"):
        validate_schema_version_compatibility(payload, schema, compatibility_level="major")

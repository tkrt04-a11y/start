"""JSON schema validation helpers for machine-readable CLI outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator


_SEMVER_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def load_json_schema(schema_path: str | Path) -> dict[str, Any]:
    path = Path(schema_path)
    with path.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    if not isinstance(schema, dict):
        raise ValueError(f"Schema must be an object: {path}")
    Draft202012Validator.check_schema(schema)
    return schema


def validate_json_payload(payload: Any, schema: dict[str, Any], *, schema_name: str = "schema") -> None:
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.path))
    if not errors:
        return

    first = errors[0]
    path = ".".join(str(item) for item in first.path)
    location = path or "<root>"
    raise ValueError(f"JSON schema validation failed ({schema_name}) at {location}: {first.message}")


def _parse_semver(version: str) -> tuple[int, int, int]:
    match = _SEMVER_PATTERN.fullmatch(version.strip())
    if not match:
        raise ValueError(f"Invalid schema_version format: {version!r}. Expected MAJOR.MINOR.PATCH")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _extract_supported_schema_versions(schema: dict[str, Any]) -> list[str]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []

    schema_version_def = properties.get("schema_version")
    if not isinstance(schema_version_def, dict):
        return []

    const_version = schema_version_def.get("const")
    if isinstance(const_version, str) and const_version.strip():
        return [const_version.strip()]

    enum_versions = schema_version_def.get("enum")
    if isinstance(enum_versions, list):
        normalized: list[str] = []
        for value in enum_versions:
            if isinstance(value, str) and value.strip():
                normalized.append(value.strip())
        return normalized

    return []


def validate_schema_version_compatibility(
    payload: Any,
    schema: dict[str, Any],
    *,
    compatibility_level: str = "major",
    schema_name: str = "schema",
) -> None:
    if compatibility_level == "none":
        return
    if compatibility_level != "major":
        raise ValueError(f"Unsupported compatibility level: {compatibility_level}")

    if not isinstance(payload, dict):
        raise ValueError("schema_version compatibility check requires JSON object payload")

    payload_schema_version = payload.get("schema_version")
    if not isinstance(payload_schema_version, str) or not payload_schema_version.strip():
        raise ValueError("schema_version compatibility check failed: payload.schema_version is required")

    payload_major, _, _ = _parse_semver(payload_schema_version)

    supported_versions = _extract_supported_schema_versions(schema)
    if not supported_versions:
        raise ValueError(
            f"schema_version compatibility check failed: no schema_version const/enum defined in {schema_name}"
        )

    supported_majors: set[int] = set()
    for supported_version in supported_versions:
        major, _, _ = _parse_semver(supported_version)
        supported_majors.add(major)

    if payload_major not in supported_majors:
        raise ValueError(
            "schema_version compatibility check failed: "
            f"major version mismatch (payload={payload_schema_version}, supported={supported_versions})"
        )


def validate_json_file(input_path: str | Path, schema_path: str | Path, *, compatibility_level: str = "none") -> None:
    schema = load_json_schema(schema_path)
    payload_path = Path(input_path)
    raw = payload_path.read_bytes()
    payload_text: str | None = None
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            payload_text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if payload_text is None:
        raise ValueError(f"Unable to decode JSON input with supported encodings: {payload_path}")
    payload = json.loads(payload_text)
    validate_schema_version_compatibility(
        payload,
        schema,
        compatibility_level=compatibility_level,
        schema_name=str(schema_path),
    )
    validate_json_payload(payload, schema, schema_name=str(schema_path))


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate JSON file with JSON schema.")
    parser.add_argument("--input", required=True, help="Input JSON file path")
    parser.add_argument("--schema", required=True, help="JSON schema file path")
    parser.add_argument(
        "--compatibility",
        choices=["none", "major"],
        default="major",
        help="schema_version compatibility check level (default: major)",
    )
    return parser


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()
    validate_json_file(args.input, args.schema, compatibility_level=args.compatibility)
    print(
        "Schema validation passed: "
        f"input={args.input} schema={args.schema} compatibility={args.compatibility}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

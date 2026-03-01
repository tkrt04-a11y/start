# JSON Schema Compatibility Policy

This document defines compatibility rules for JSON Schemas under `docs/schemas/` (currently `metrics_check.schema.json` and `ops_report.schema.json`).

## 1. Schema location and ownership

- Canonical schema location is `docs/schemas/`.
- In generated projects, this policy applies to `docs/schemas/` directly.
- Manage each schema file as one contract for one machine-readable output.

## 2. Versioning policy

- Classify schema changes with SemVer (`MAJOR.MINOR.PATCH`):
  - `MAJOR`: breaking change (no backward compatibility)
  - `MINOR`: backward-compatible additions (for example optional fields)
  - `PATCH`: non-semantic fixes (wording, typo, safe constraint relaxations)
- Declare the compatibility class in PR description and/or related documentation updates.

## 3. Compatibility rules

### Backward compatibility

Existing consumers should continue to read data produced after schema updates.

Preferred changes:
- Add optional properties
- Improve descriptions
- Relax validation constraints without invalidating previously valid payloads

### Forward compatibility

New consumers should continue to read old payloads.

Preferred approach:
- Introduce new fields as optional first, then phase in required usage if needed
- Keep readers tolerant to unknown fields

## 4. Breaking change rules

Treat these as breaking by default:

- Adding entries to `required`
- Removing or renaming existing properties
- Changing property types (for example `string` to `number`)
- Removing enum values or tightening constraints that invalidate existing payloads

When a breaking change is necessary:
- Mark PR title or description with `BREAKING`
- Document impact (producer/consumer/CI) and migration steps in the same PR
- Add a transition window when old/new payload formats need to coexist

## 5. Update workflow (where and how)

1. Update target schema in `docs/schemas/*.schema.json`.
2. Keep all related schema files in `docs/schemas/*.schema.json` aligned in the same change.
3. Update this policy and related references in `README.md` as needed.
4. Validate representative JSON outputs locally.

Examples:

```sh
python scripts/ci/validate_json_schema.py --input metrics-check-result.json --schema docs/schemas/metrics_check.schema.json
python scripts/ci/validate_json_schema.py --input logs/ops-report-ci.json --schema docs/schemas/ops_report.schema.json
```

## 6. CI operation policy

- CI should continuously verify JSON outputs against their schemas.
- Schema-change PRs should keep schema, producer, and consumer updates in one PR.
- PRs that affect compatibility should declare `MAJOR/MINOR/PATCH` classification.
- Breaking changes should include migration notes as a review requirement.

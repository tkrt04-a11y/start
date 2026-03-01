from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_payload(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"finding_count": 0, "findings": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"finding_count": 0, "findings": []}
    if not isinstance(payload, dict):
        return {"finding_count": 0, "findings": []}
    findings = payload.get("findings", [])
    if not isinstance(findings, list):
        findings = []
    return {
        "finding_count": int(payload.get("finding_count", len(findings)) or 0),
        "findings": findings,
    }


def _fingerprint(item: dict[str, Any]) -> str:
    package = str(item.get("package", "")).strip().lower()
    version = str(item.get("version", "")).strip().lower()
    advisory_id = str(item.get("id", "")).strip().lower()
    return f"{package}|{version}|{advisory_id}"


def compare_snapshots(current_payload: dict[str, Any], previous_payload: dict[str, Any]) -> dict[str, Any]:
    current_rows = [item for item in current_payload.get("findings", []) if isinstance(item, dict)]
    previous_rows = [item for item in previous_payload.get("findings", []) if isinstance(item, dict)]

    current_map = {_fingerprint(item): item for item in current_rows}
    previous_map = {_fingerprint(item): item for item in previous_rows}

    newly = [current_map[key] for key in sorted(current_map.keys() - previous_map.keys())]
    resolved = [previous_map[key] for key in sorted(previous_map.keys() - current_map.keys())]

    return {
        "current_count": len(current_rows),
        "previous_count": len(previous_rows),
        "newly_detected": newly,
        "resolved": resolved,
    }


def render_markdown(result: dict[str, Any]) -> str:
    newly = result.get("newly_detected", [])
    resolved = result.get("resolved", [])
    lines = [
        "<!-- ai-starter:dependency-vuln -->",
        "## Dependency Vulnerability Diff",
        "",
        f"- Current findings: {int(result.get('current_count', 0))}",
        f"- Previous findings: {int(result.get('previous_count', 0))}",
        f"- Newly detected: {len(newly)}",
        f"- Resolved: {len(resolved)}",
        "",
        "### Newly detected",
    ]
    if isinstance(newly, list) and newly:
        for item in newly:
            lines.append(
                f"- {item.get('package', 'unknown')}=={item.get('version', 'unknown')} "
                f"id={item.get('id', 'unknown')} severity={item.get('severity', 'unknown')}"
            )
    else:
        lines.append("- (none)")

    lines.extend(["", "### Resolved"])
    if isinstance(resolved, list) and resolved:
        for item in resolved:
            lines.append(
                f"- {item.get('package', 'unknown')}=={item.get('version', 'unknown')} "
                f"id={item.get('id', 'unknown')} severity={item.get('severity', 'unknown')}"
            )
    else:
        lines.append("- (none)")

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare dependency vulnerability snapshots")
    parser.add_argument("--current", required=True, help="current snapshot json path")
    parser.add_argument("--previous", required=True, help="previous snapshot json path")
    parser.add_argument("--output-json", required=True, help="output json path")
    parser.add_argument("--output-md", required=True, help="output markdown path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    current_payload = _load_payload(Path(args.current))
    previous_payload = _load_payload(Path(args.previous))
    result = compare_snapshots(current_payload, previous_payload)

    output_json_path = Path(args.output_json)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")

    output_md_path = Path(args.output_md)
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.write_text(render_markdown(result), encoding="utf-8")

    print(
        f"Dependency vulnerability diff: current={result['current_count']} previous={result['previous_count']} "
        f"newly={len(result['newly_detected'])} resolved={len(result['resolved'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

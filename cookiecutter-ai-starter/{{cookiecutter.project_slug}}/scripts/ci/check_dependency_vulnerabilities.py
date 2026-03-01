from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

SEVERITY_RANK = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

DEFAULT_FAIL_LEVEL = "high"
FAIL_LEVEL_ENV = "DEPENDENCY_VULN_FAIL_LEVEL"


def normalize_fail_level(value: str | None) -> str:
    text = (value or "").strip().lower()
    if text in SEVERITY_RANK:
        return text
    return DEFAULT_FAIL_LEVEL


def extract_cvss_score(raw_text: str) -> float | None:
    matched = re.search(r"CVSS:(?:\d\.\d/)?([A-Z]{1,2}:[A-Z](?:/[A-Z]{1,2}:[A-Z])*)", raw_text)
    if not matched:
        return None

    vector = matched.group(1)
    if "C:H" in vector and "I:H" in vector and "A:H" in vector:
        return 9.8
    if "C:H" in vector or "I:H" in vector or "A:H" in vector:
        return 7.5
    if "C:L" in vector or "I:L" in vector or "A:L" in vector:
        return 5.0
    return 3.5


def score_to_level(score: float | None) -> str:
    if score is None:
        return "high"
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    return "low"


def vulnerability_severity(vulnerability: dict[str, Any]) -> str:
    severity_payload = vulnerability.get("severity", [])
    if not isinstance(severity_payload, list):
        return "high"

    best_rank = 0
    best_level = "high"
    for item in severity_payload:
        if not isinstance(item, dict):
            continue
        score_value = item.get("score")
        if not isinstance(score_value, str):
            continue

        level = "high"
        text = score_value.strip()
        score_num: float | None = None
        if text.upper().startswith("CVSS:"):
            score_num = extract_cvss_score(text)
        else:
            try:
                score_num = float(text)
            except ValueError:
                score_num = None
        level = score_to_level(score_num)
        rank = SEVERITY_RANK.get(level, 0)
        if rank > best_rank:
            best_rank = rank
            best_level = level

    return best_level


def run_pip_audit(requirements_file: Path) -> dict[str, Any]:
    process = subprocess.run(
        [
            "python",
            "-m",
            "pip_audit",
            "-r",
            str(requirements_file),
            "-f",
            "json",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    output_text = process.stdout.strip()
    if not output_text:
        output_text = "[]"

    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse pip-audit JSON output: {exc}\nstdout={output_text}\nstderr={process.stderr}") from exc

    if isinstance(payload, list):
        return {"dependencies": payload}
    if isinstance(payload, dict):
        return payload
    raise RuntimeError("Unexpected pip-audit output format")


def collect_findings(payload: dict[str, Any]) -> list[dict[str, str]]:
    dependencies = payload.get("dependencies", [])
    if not isinstance(dependencies, list):
        return []

    findings: list[dict[str, str]] = []
    for dep in dependencies:
        if not isinstance(dep, dict):
            continue
        package_name = str(dep.get("name", "")).strip() or "unknown"
        package_version = str(dep.get("version", "")).strip() or "unknown"
        vulns = dep.get("vulns", [])
        if not isinstance(vulns, list):
            continue

        for vuln in vulns:
            if not isinstance(vuln, dict):
                continue
            advisory_id = str(vuln.get("id", "")).strip() or "unknown"
            severity = vulnerability_severity(vuln)
            findings.append(
                {
                    "package": package_name,
                    "version": package_version,
                    "id": advisory_id,
                    "severity": severity,
                }
            )
    return findings


def should_fail(findings: list[dict[str, str]], fail_level: str) -> bool:
    threshold_rank = SEVERITY_RANK[fail_level]
    for item in findings:
        if SEVERITY_RANK.get(item.get("severity", ""), 0) >= threshold_rank:
            return True
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run dependency vulnerability scan and fail by severity threshold")
    parser.add_argument("--requirements", default="requirements.txt", help="requirements file path")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="output format")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    requirements_file = Path(args.requirements)
    if not requirements_file.is_file():
        raise SystemExit(f"requirements file not found: {requirements_file.as_posix()}")

    fail_level = normalize_fail_level(os.getenv(FAIL_LEVEL_ENV))
    payload = run_pip_audit(requirements_file)
    findings = collect_findings(payload)

    if args.format == "json":
        print(
            json.dumps(
                {
                    "fail_level": fail_level,
                    "finding_count": len(findings),
                    "findings": findings,
                },
                ensure_ascii=False,
            )
        )
    else:
        print(f"Dependency vulnerability scan: findings={len(findings)} fail_level={fail_level}")
        for item in findings:
            print(
                f"- {item['package']}=={item['version']} id={item['id']} severity={item['severity']}"
            )

    return 1 if should_fail(findings, fail_level) else 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def parse_outcomes(values: list[str] | None) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    for pair in values or []:
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        key = key.strip()
        value = value.strip().lower()
        if key:
            outcomes[key] = value
    return outcomes


def _is_failed(outcome: str) -> bool:
    return outcome in {"failure", "cancelled", "timed_out"}


def build_decision(outcomes: dict[str, str], dependency_blockers: bool) -> dict[str, object]:
    failed_steps = [name for name, outcome in outcomes.items() if _is_failed(outcome)]

    risk_level = "low"
    impact_scope = "limited"
    recommendation = "fix-forward"
    rationale = "No critical quality gate failure detected."

    if dependency_blockers:
        risk_level = "high"
        impact_scope = "moderate"
        recommendation = "block-release-fix-dependencies"
        rationale = "Dependency vulnerabilities exceeded configured severity threshold."

    if any(step in failed_steps for step in ["run_tests", "doctor_check"]):
        risk_level = "high"
        impact_scope = "broad"
        recommendation = "rollback-recommended"
        rationale = "Core quality gates failed (tests/doctor)."
    elif any(step in failed_steps for step in ["metrics_check", "validate_metrics_schema", "validate_ops_schema"]):
        risk_level = "medium"
        impact_scope = "moderate"
        recommendation = "hold-and-investigate"
        rationale = "Operational quality gate failed; validate production risk before release."

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "risk_level": risk_level,
        "impact_scope": impact_scope,
        "recommendation": recommendation,
        "rationale": rationale,
        "dependency_blockers": dependency_blockers,
        "failed_steps": failed_steps,
        "outcomes": outcomes,
    }


def render_markdown(decision: dict[str, object]) -> str:
    failed_steps = decision.get("failed_steps", [])
    outcomes = decision.get("outcomes", {})
    lines = [
        "# CI Rollback Decision",
        "",
        f"- Generated at (UTC): {decision.get('generated_at', '')}",
        f"- Risk level: {decision.get('risk_level', 'unknown')}",
        f"- Impact scope: {decision.get('impact_scope', 'unknown')}",
        f"- Recommendation: {decision.get('recommendation', 'unknown')}",
        f"- Dependency blockers: {str(bool(decision.get('dependency_blockers', False))).lower()}",
        "",
        "## Rationale",
        f"- {decision.get('rationale', '')}",
        "",
        "## Failed Steps",
    ]
    if isinstance(failed_steps, list) and failed_steps:
        for step in failed_steps:
            lines.append(f"- {step}")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Step Outcomes"])
    if isinstance(outcomes, dict) and outcomes:
        for key in sorted(outcomes.keys()):
            lines.append(f"- {key}: {outcomes[key]}")
    else:
        lines.append("- (none)")

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate CI rollback decision report")
    parser.add_argument("--outcome", action="append", default=None, help="step outcome in key=value format")
    parser.add_argument("--dependency-blockers", default="false", help="true when dependency vuln gate blocks")
    parser.add_argument("--output-json", required=True, help="output json path")
    parser.add_argument("--output-md", required=True, help="output markdown path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outcomes = parse_outcomes(args.outcome)
    dependency_blockers = str(args.dependency_blockers).strip().lower() in {"1", "true", "yes", "on"}
    decision = build_decision(outcomes, dependency_blockers)

    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(decision, ensure_ascii=False), encoding="utf-8")

    output_md = Path(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(decision), encoding="utf-8")

    print(
        f"CI rollback decision generated: recommendation={decision['recommendation']} "
        f"risk={decision['risk_level']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

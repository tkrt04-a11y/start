from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable

PATTERNS = {
    "openai_api_key": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "github_pat": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "github_pat_new": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH|DSA|PRIVATE) KEY-----"),
    "slack_webhook": re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]+"),
}

ALLOWLIST_REGEX = [
    re.compile(r"\bsk-\.\.\.\b"),
    re.compile(r"\byour_api_key_here\b", re.IGNORECASE),
]

TEXT_EXTENSIONS = {
    ".py", ".ps1", ".md", ".yml", ".yaml", ".json", ".txt", ".ini", ".cfg", ".toml", ".env", ""
}


def _is_probably_text(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    return path.name in {"Dockerfile", ".env.example"}


def _iter_paths_from_git(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=str(root),
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return []

    paths: list[Path] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        candidate = root / line.strip()
        if candidate.is_file():
            paths.append(candidate)
    return paths


def _is_allowlisted(text: str) -> bool:
    return any(pattern.search(text) for pattern in ALLOWLIST_REGEX)


def scan_paths(paths: Iterable[Path], root: Path) -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    for path in paths:
        if not _is_probably_text(path):
            continue

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for index, line in enumerate(content.splitlines(), start=1):
            if _is_allowlisted(line):
                continue
            for pattern_name, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(
                        {
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "line": index,
                            "pattern": pattern_name,
                            "excerpt": line.strip()[:200],
                        }
                    )
    return findings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan repository text files for possible committed secrets")
    parser.add_argument("--path", action="append", dest="paths", default=None, help="Relative file path to scan")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    root = Path.cwd()

    if args.paths:
        targets = [root / item for item in args.paths]
    else:
        targets = _iter_paths_from_git(root)

    findings = scan_paths(targets, root)
    if args.format == "json":
        import json

        print(json.dumps({"findings": findings}, ensure_ascii=False))
    else:
        if findings:
            print("Potential secrets detected:")
            for finding in findings:
                print(
                    f"- {finding['path']}:{finding['line']} ({finding['pattern']}) {finding['excerpt']}"
                )
        else:
            print("Secret scan passed. No findings.")

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

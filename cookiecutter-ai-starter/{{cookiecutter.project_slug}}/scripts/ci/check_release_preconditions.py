from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate release workflow preconditions")
    parser.add_argument("--tag", required=True, help="release tag name")
    parser.add_argument("--notes-file", required=True, help="release notes file path")
    parser.add_argument("--target", required=True, help="target branch or commit")
    parser.add_argument("--github-ref-name", default="", help="GitHub ref name")
    parser.add_argument("--repo-root", default=".", help="repository root")
    return parser.parse_args()


def validate_notes_file(notes_file: Path) -> str | None:
    if notes_file.is_file():
        return None
    return f"Release notes file not found: {notes_file.as_posix()}"


def validate_clean_worktree(repo_root: Path) -> str | None:
    status = run_git(["status", "--porcelain"], cwd=repo_root)
    if status.returncode != 0:
        return f"Failed to verify git status: {status.stderr.strip()}"
    if status.stdout.strip():
        return "Working tree is not clean. Commit or stash changes before release."
    return None


def validate_target_exists(repo_root: Path, target: str) -> str | None:
    resolved = run_git(["rev-parse", "--verify", f"{target}^{{commit}}"], cwd=repo_root)
    if resolved.returncode == 0:
        return None
    return f"Target branch/commit not found: {target}"


def validate_target_ref_consistency(target: str, github_ref_name: str) -> str | None:
    normalized_target = target.strip().removeprefix("refs/heads/")
    if not normalized_target or not github_ref_name:
        return None

    is_probably_sha = len(normalized_target) >= 7 and all(c in "0123456789abcdef" for c in normalized_target.lower())
    if is_probably_sha:
        return None

    if normalized_target != github_ref_name.strip():
        return (
            "Target branch mismatch: "
            f"workflow ref={github_ref_name.strip()} target={normalized_target}."
        )
    return None


def validate_tag_not_exists(repo_root: Path, tag: str) -> str | None:
    local = run_git(["rev-parse", "--verify", f"refs/tags/{tag}"], cwd=repo_root)
    if local.returncode == 0:
        return f"Tag already exists locally: {tag}"

    remote = run_git(["ls-remote", "--tags", "origin", f"refs/tags/{tag}"], cwd=repo_root)
    if remote.returncode != 0:
        return f"Failed to query remote tags: {remote.stderr.strip()}"
    if remote.stdout.strip():
        return f"Tag already exists on remote: {tag}"
    return None


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    notes_file = (repo_root / args.notes_file).resolve()

    checks = [
        validate_notes_file(notes_file),
        validate_clean_worktree(repo_root),
        validate_target_exists(repo_root, args.target),
        validate_target_ref_consistency(args.target, args.github_ref_name),
        validate_tag_not_exists(repo_root, args.tag),
    ]
    errors = [item for item in checks if item]

    if errors:
        print("Release precondition check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Release precondition check: OK")
    print(f"- tag={args.tag}")
    print(f"- target={args.target}")
    print(f"- notes_file={args.notes_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

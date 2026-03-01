"""Environment file helpers."""

from __future__ import annotations

from pathlib import Path


def ensure_env_from_example(
    example_path: Path | str = ".env.example",
    env_path: Path | str = ".env",
) -> dict[str, int]:
    example = Path(example_path)
    target = Path(env_path)

    if not example.exists():
        return {"created": 0, "added": 0, "missing_example": 1}

    example_lines = example.read_text(encoding="utf-8").splitlines()

    if target.exists():
        current_lines = target.read_text(encoding="utf-8").splitlines()
    else:
        current_lines = []

    current_keys = {
        line.split("=", 1)[0].strip()
        for line in current_lines
        if line.strip() and not line.strip().startswith("#") and "=" in line
    }

    appended: list[str] = []
    for line in example_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key not in current_keys:
            appended.append(line)
            current_keys.add(key)

    created = 0
    if not target.exists():
        target.write_text("", encoding="utf-8")
        created = 1

    if appended:
        with target.open("a", encoding="utf-8") as f:
            if target.read_text(encoding="utf-8") and not target.read_text(encoding="utf-8").endswith("\n"):
                f.write("\n")
            f.write("\n".join(appended) + "\n")

    return {"created": created, "added": len(appended), "missing_example": 0}

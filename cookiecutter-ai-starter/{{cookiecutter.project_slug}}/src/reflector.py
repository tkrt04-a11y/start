"""Apply analysis insights back into starter-kit artifacts."""

from __future__ import annotations

from pathlib import Path
from datetime import date


def _priority_rank(action_text: str) -> int:
    if action_text.startswith("[High]"):
        return 0
    if action_text.startswith("[Med]"):
        return 1
    if action_text.startswith("[Low]"):
        return 2
    return 3


def generate_backlog_markdown(
    summary: dict[str, int],
    ai_summary: str = "",
    spotlight_actions: list[str] | None = None,
    promoted_actions: list[str] | None = None,
) -> str:
    lines: list[str] = []
    lines.append("# Improvement Backlog")
    lines.append("")
    lines.append(f"Generated: {date.today().isoformat()}")
    lines.append("")
    lines.append("## Promoted This Week")
    if promoted_actions:
        for action in list(dict.fromkeys(promoted_actions))[:5]:
            lines.append(f"- [ ] {action}")
    else:
        lines.append("- [ ] No promoted actions found")
    lines.append("")
    lines.append("## Source Counts")
    if summary:
        for source, count in sorted(summary.items(), key=lambda item: item[1], reverse=True):
            lines.append(f"- {source}: {count}")
    else:
        lines.append("- No collected entries yet.")
    lines.append("")
    lines.append("## AI Insights")
    lines.append(ai_summary.strip() if ai_summary.strip() else "- AI summary not available.")
    lines.append("")
    lines.append("## Spotlight Actions")
    if spotlight_actions:
        ordered_actions = sorted(spotlight_actions, key=_priority_rank)
        for action in ordered_actions[:5]:
            lines.append(f"- [ ] {action}")
    else:
        lines.append("- [ ] No spotlight actions extracted yet")
    lines.append("")
    lines.append("## Candidate Actions")
    lines.append("- [ ] Add or refine template modules based on top recurring theme")
    lines.append("- [ ] Expand test cases for pain points found in collected notes")
    lines.append("- [ ] Update README quickstart to address top confusion areas")
    lines.append("- [ ] Add one automation script that removes manual repetitive setup")
    lines.append("")
    return "\n".join(lines)


def write_backlog(
    summary: dict[str, int],
    ai_summary: str = "",
    spotlight_actions: list[str] | None = None,
    promoted_actions: list[str] | None = None,
    output_path: Path | str = "docs/improvement_backlog.md",
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        generate_backlog_markdown(
            summary,
            ai_summary,
            spotlight_actions=spotlight_actions,
            promoted_actions=promoted_actions,
        ),
        encoding="utf-8",
    )
    return path


def update_instruction_file(
    top_sources: list[str],
    instruction_path: Path | str = ".github/instructions/common.instructions.md",
) -> Path:
    path = Path(instruction_path)
    if path.exists():
        current = path.read_text(encoding="utf-8")
    else:
        current = ""

    updated = render_instruction_markdown(current, top_sources)

    path.write_text(updated, encoding="utf-8")
    return path


def render_instruction_markdown(current: str, top_sources: list[str]) -> str:

    marker_start = "<!-- auto-insights:start -->"
    marker_end = "<!-- auto-insights:end -->"

    block_lines = [marker_start, "## Auto Insights", "収集データから頻出した情報源（上位）:"]
    if top_sources:
        for source in top_sources[:5]:
            block_lines.append(f"- {source}")
    else:
        block_lines.append("- まだデータがありません")
    block_lines.append(marker_end)
    block = "\n".join(block_lines)

    if marker_start in current and marker_end in current:
        start = current.find(marker_start)
        end = current.find(marker_end) + len(marker_end)
        prefix = current[:start].rstrip()
        if prefix:
            updated = prefix + "\n\n" + block + "\n"
        else:
            updated = block + "\n"
    else:
        spacer = "\n\n" if current and not current.endswith("\n") else ("\n" if current else "")
        updated = current + spacer + block + "\n"
    return updated

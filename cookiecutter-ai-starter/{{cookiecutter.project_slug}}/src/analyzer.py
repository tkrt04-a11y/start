"""Basic analysis utilities for collected information."""

from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Iterable

from src import models


def load_entries(path: Path | str = "collected_data.json") -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except json.JSONDecodeError:
        pass
    return []


def summarize_by_source(entries: Iterable[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in entries:
        src = e.get("source", "<unknown>")
        counts[src] = counts.get(src, 0) + 1
    return counts


def pretty_print_summary(summary: dict[str, int]) -> None:
    if not summary:
        print("No data to analyze.")
        return
    print("Entries by source:")
    for src, cnt in summary.items():
        print(f"  {src}: {cnt}")


def generate_ai_summary(
    entries: Iterable[dict],
    api_key: str,
    model: str = "gpt-4o-mini",
) -> str:
    entry_list = list(entries)
    if not entry_list:
        return "No data to analyze."

    prompt_lines = []
    for entry in entry_list[:200]:
        src = entry.get("source", "unknown")
        content = str(entry.get("content", ""))
        prompt_lines.append(f"- [{src}] {content}")

    prompt = (
        "You are helping improve an AI-driven development starter kit.\n"
        "Given the collected notes below, provide concise themes and actions.\n\n"
        "Collected notes:\n"
        + "\n".join(prompt_lines)
    )

    client = models.get_openai_client(api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return response.choices[0].message.content or ""


def generate_fallback_summary(entries: Iterable[dict]) -> str:
    entry_list = list(entries)
    if not entry_list:
        return "No data to analyze."

    source_counts = summarize_by_source(entry_list)
    top_sources = sorted(source_counts.items(), key=lambda item: item[1], reverse=True)[:5]

    keyword_counts: dict[str, int] = {}
    stopwords = {
        "the", "and", "for", "with", "that", "this", "from", "are", "you", "your",
        "http", "https", "www", "com", "org", "net", "github", "issue", "open",
    }

    for entry in entry_list:
        text = str(entry.get("content", "")).lower()
        for token in re.findall(r"\w+", text):
            if len(token) < 3 or token in stopwords:
                continue
            keyword_counts[token] = keyword_counts.get(token, 0) + 1

    top_keywords = sorted(keyword_counts.items(), key=lambda item: item[1], reverse=True)[:8]

    lines: list[str] = []
    lines.append("Fallback summary (local heuristics)")
    lines.append("")
    lines.append("Top sources:")
    for source, count in top_sources:
        lines.append(f"- {source}: {count}")
    lines.append("")
    lines.append("Recurring keywords:")
    if top_keywords:
        for keyword, count in top_keywords:
            lines.append(f"- {keyword}: {count}")
    else:
        lines.append("- Not enough textual data")
    lines.append("")
    lines.append("Suggested actions:")
    lines.append("- Prioritize improvements around the top source")
    lines.append("- Turn recurring keywords into concrete backlog tasks")
    lines.append("- Add tests/docs for the most repeated pain points")
    return "\n".join(lines)

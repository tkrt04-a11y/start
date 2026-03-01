"""Entry point for the AI starter kit."""
from datetime import datetime, timedelta
from difflib import ndiff
import json
import os
from pathlib import Path
import re
import sys
from src import models
from src.collector import DataCollector
from src.analyzer import (
    load_entries,
    summarize_by_source,
    pretty_print_summary,
    generate_ai_summary,
    generate_fallback_summary,
)
from src.connectors import fetch_github_issues, fetch_rss_feed, fetch_survey_json
from src.reflector import generate_backlog_markdown, render_instruction_markdown, write_backlog, update_instruction_file
from src.issue_sync import parse_issue_assignee_rules, resolve_issue_assignees, sync_promoted_actions_to_github_issues
from src.doctor import print_doctor_report, print_doctor_report_json
from src.env_tools import ensure_env_from_example
from src.reporter import (
    write_weekly_report,
    write_monthly_report,
    filter_entries_by_days,
    filter_entries_between,
    extract_spotlight_action_items_from_markdown,
    extract_promoted_actions_from_markdown,
    extract_monthly_promoted_actions_from_markdown,
)
from src.activity_log import append_activity
from src.alert_dedup import prune_alert_dedup_state, reset_alert_dedup_state, summarize_alert_dedup_state
from src.metrics import build_metrics_summary, check_metric_thresholds, format_metrics_summary_text
from src.ops_report import generate_and_write_ops_report
from src.ops_report_index import write_ops_reports_index
from src.retention import run_retention
from src.schema_versions import SCHEMA_VERSION


WEEKLY_REPORT_LABEL_PATTERN = re.compile(r"^#\s+Weekly Report\s*\((\d{4}-W\d{2})\)", re.MULTILINE)
MONTHLY_REPORT_LABEL_PATTERN = re.compile(r"^#\s+Monthly Report\s*\((\d{4}-\d{2})\)", re.MULTILINE)
DEFAULT_ALERT_DEDUP_STATE_PATH = Path("logs/alert_dedup_state.json")


def _extract_period_key_from_weekly_report(markdown_text: str) -> str:
    match = WEEKLY_REPORT_LABEL_PATTERN.search(markdown_text)
    if not match:
        return ""
    return match.group(1).strip()


def _extract_period_key_from_monthly_report(markdown_text: str) -> str:
    match = MONTHLY_REPORT_LABEL_PATTERN.search(markdown_text)
    if not match:
        return ""
    return match.group(1).strip()


def handle_collect(args: list[str]) -> None:
    if len(args) >= 1:
        source = args[0]
    else:
        source = input("Source? ")

    if len(args) >= 2:
        content = args[1]
    else:
        content = input("Content? ")

    collector = DataCollector()
    collector.collect(source, content)
    append_activity("collect", {"source": source, "content_preview": content[:120]})
    print("Information collected.")


def handle_analyze(args: list[str]) -> None:
    entries = load_entries()
    summary = summarize_by_source(entries)
    pretty_print_summary(summary)
    append_activity("analyze", {"entry_count": len(entries), "use_ai": "--ai" in args})

    if "--ai" in args:
        model = "gpt-4o-mini"
        if "--model" in args:
            idx = args.index("--model")
            if idx + 1 < len(args):
                model = args[idx + 1]

        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                ai_summary = generate_ai_summary(entries, api_key=api_key, model=model)
            except Exception as e:
                print(f"AI API error ({type(e).__name__}). Using local fallback summary.")
                ai_summary = generate_fallback_summary(entries)
        else:
            print("OPENAI_API_KEY is not set. Using local fallback summary.")
            ai_summary = generate_fallback_summary(entries)
        print("\nAI summary:\n")
        print(ai_summary)


def handle_fetch(args: list[str]) -> None:
    if not args:
        print("Usage: fetch <github|rss|survey-json> ...")
        return

    collector = DataCollector()
    connector = args[0]

    if connector == "github":
        if len(args) < 2:
            print("Usage: fetch github <owner/repo> [state] [limit]")
            return
        repo = args[1]
        state = args[2] if len(args) >= 3 else "open"
        limit = int(args[3]) if len(args) >= 4 else 20
        entries = fetch_github_issues(repo, state=state, limit=limit)
    elif connector == "rss":
        if len(args) < 2:
            print("Usage: fetch rss <feed_url> [limit]")
            return
        feed_url = args[1]
        limit = int(args[2]) if len(args) >= 3 else 20
        entries = fetch_rss_feed(feed_url, limit=limit)
    elif connector == "survey-json":
        if len(args) < 2:
            print("Usage: fetch survey-json <path> [content_field]")
            return
        path = args[1]
        content_field = args[2] if len(args) >= 3 else "content"
        entries = fetch_survey_json(path, content_field=content_field)
    else:
        print(f"Unknown connector: {connector}")
        return

    for entry in entries:
        collector.collect(entry["source"], entry["content"])
    append_activity("fetch", {"connector": connector, "fetched_count": len(entries)})
    print(f"Fetched and stored {len(entries)} entries.")


def handle_apply_insights(args: list[str]) -> None:
    dry_run = "--dry-run" in args
    entries = load_entries()
    summary = summarize_by_source(entries)

    ai_summary = ""
    if "--ai" in args:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                ai_summary = generate_ai_summary(entries, api_key=api_key)
            except Exception as e:
                print(f"AI API error ({type(e).__name__}). Using local fallback summary.")
                ai_summary = generate_fallback_summary(entries)
        else:
            ai_summary = generate_fallback_summary(entries)

    spotlight_actions: list[str] = []
    promoted_actions: list[str] = []
    weekly_period_key = ""
    monthly_promoted_actions: list[str] = []
    monthly_period_key = ""
    weekly_latest = "docs/weekly_reports/latest_weekly_report.md"
    if os.path.exists(weekly_latest):
        with open(weekly_latest, "r", encoding="utf-8") as f:
            weekly_markdown = f.read()
        weekly_period_key = _extract_period_key_from_weekly_report(weekly_markdown)
        spotlight_items = extract_spotlight_action_items_from_markdown(weekly_markdown)
        spotlight_actions = [f"[{item['priority']}] {item['action']}" for item in spotlight_items]
        promoted_actions = extract_promoted_actions_from_markdown(weekly_markdown)

    monthly_latest = "docs/monthly_reports/latest_monthly_report.md"
    if os.path.exists(monthly_latest):
        with open(monthly_latest, "r", encoding="utf-8") as f:
            monthly_markdown = f.read()
        monthly_period_key = _extract_period_key_from_monthly_report(monthly_markdown)
        monthly_promoted_actions = extract_monthly_promoted_actions_from_markdown(monthly_markdown)

    def summarize_diff(target_path: str, prospective_content: str) -> tuple[str, int, int]:
        path = Path(target_path)
        if not path.exists():
            return "new_file", len(prospective_content.splitlines()), 0

        current_content = path.read_text(encoding="utf-8")
        if current_content == prospective_content:
            return "unchanged", 0, 0

        added_lines = 0
        removed_lines = 0
        for line in ndiff(current_content.splitlines(), prospective_content.splitlines()):
            if line.startswith("+ "):
                added_lines += 1
            elif line.startswith("- "):
                removed_lines += 1
        return "changed", added_lines, removed_lines

    if dry_run:
        backlog_path = "docs/improvement_backlog.md"
        instruction_path = ".github/instructions/common.instructions.md"

        backlog_content = generate_backlog_markdown(
            summary,
            ai_summary,
            spotlight_actions=spotlight_actions,
            promoted_actions=promoted_actions,
        )
        top_sources = [k for k, _ in sorted(summary.items(), key=lambda item: item[1], reverse=True)]

        instruction_file = Path(instruction_path)
        instruction_current = ""
        if instruction_file.exists():
            instruction_current = instruction_file.read_text(encoding="utf-8")
        instruction_content = render_instruction_markdown(instruction_current, top_sources)

        backlog_status, backlog_added, backlog_removed = summarize_diff(backlog_path, backlog_content)
        instruction_status, instruction_added, instruction_removed = summarize_diff(instruction_path, instruction_content)

        print("Dry-run: no files were written.")
        print(f"backlog: {backlog_status} (+{backlog_added}/-{backlog_removed} lines)")
        print(f"instructions: {instruction_status} (+{instruction_added}/-{instruction_removed} lines)")
    else:
        backlog_path = write_backlog(
            summary,
            ai_summary=ai_summary,
            spotlight_actions=spotlight_actions,
            promoted_actions=promoted_actions,
        )
        top_sources = [k for k, _ in sorted(summary.items(), key=lambda item: item[1], reverse=True)]
        instruction_path = update_instruction_file(top_sources)
        print(f"Updated: {backlog_path}")
        print(f"Updated: {instruction_path}")
    print(f"Synced Spotlight actions: {len(spotlight_actions)}")
    print(f"Synced Promoted actions: {len(promoted_actions)}")
    print(f"Synced Monthly Promoted actions: {len(monthly_promoted_actions)}")

    promoted_threshold = 1
    threshold_text = os.getenv("PROMOTED_MIN_COUNT", "1").strip()
    if threshold_text:
        try:
            promoted_threshold = max(0, int(threshold_text))
        except ValueError:
            promoted_threshold = 1

    if len(promoted_actions) < promoted_threshold:
        print(f"Warning: promoted actions below threshold ({len(promoted_actions)} < {promoted_threshold}).")

    issue_sync_enabled = os.getenv("AUTO_SYNC_PROMOTED_ISSUES", "").strip().lower() in {"1", "true", "yes", "on"}
    if "--sync-issues" in args:
        issue_sync_enabled = True
    issue_sync_created = 0
    issue_sync_failed = 0
    if issue_sync_enabled and not dry_run:
        github_repo = os.getenv("GITHUB_REPO", "").strip()
        github_token = os.getenv("GITHUB_TOKEN", "").strip()
        issue_period_labels_enabled = os.getenv("GITHUB_ISSUE_PERIOD_LABELS", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        label_text = os.getenv("GITHUB_ISSUE_LABELS", "").strip()
        assignee_text = os.getenv("GITHUB_ISSUE_ASSIGNEES", "").strip()
        assignee_rule_text = os.getenv("GITHUB_ISSUE_ASSIGNEE_RULES", "").strip()
        labels = [item.strip() for item in label_text.split(",") if item.strip()]
        assignees = [item.strip() for item in assignee_text.split(",") if item.strip()]
        issue_sync_actions: dict[str, tuple[list[str], str]] = {}
        try:
            assignee_rules = parse_issue_assignee_rules(assignee_rule_text)
            issue_sync_actions = {
                "weekly": (promoted_actions, weekly_period_key),
                "monthly": (monthly_promoted_actions, monthly_period_key),
            }
        except ValueError as exc:
            assignee_rules = {}
            issue_sync_failed += 1
            print(f"Issue sync skipped: invalid GITHUB_ISSUE_ASSIGNEE_RULES ({exc})")
        if github_repo and github_token:
            total_created = 0
            total_skipped_existing = 0
            for source_period_type, (actions, period_key) in issue_sync_actions.items():
                if not actions:
                    continue
                resolved_assignees = resolve_issue_assignees(
                    explicit_assignees=assignees,
                    labels=labels,
                    source_period_type=source_period_type,
                    include_period_label=issue_period_labels_enabled,
                    assignee_rules=assignee_rules,
                )
                result = sync_promoted_actions_to_github_issues(
                    actions,
                    github_repo,
                    github_token,
                    labels=labels,
                    assignees=resolved_assignees,
                    period_key=period_key,
                    source_period_type=source_period_type,
                    include_period_label=issue_period_labels_enabled,
                )
                total_created += result["created"]
                total_skipped_existing += result["skipped_existing"]
            issue_sync_created = total_created
            if total_created > 0 or total_skipped_existing > 0:
                print(f"Issue sync: created={total_created} skipped_existing={total_skipped_existing}")
        else:
            issue_sync_failed += 1
            print("Issue sync skipped: set GITHUB_REPO and GITHUB_TOKEN.")

    append_activity(
        "apply_insights",
        {
            "updated_backlog": str(backlog_path),
            "used_ai": "--ai" in args,
            "spotlight_actions": len(spotlight_actions),
            "promoted_actions": len(promoted_actions),
            "dry_run": dry_run,
            "issue_sync_created": issue_sync_created,
            "issue_sync_failed": issue_sync_failed,
        },
    )


def handle_weekly_report(args: list[str]) -> None:
    entries = load_entries()

    days = 7
    if "--all" in args:
        days = 0
    elif "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                days = max(0, int(args[idx + 1]))
            except ValueError:
                pass

    filtered_entries = filter_entries_by_days(entries, days=days)
    summary = summarize_by_source(filtered_entries)

    previous_summary: dict[str, int] | None = None
    if days > 0:
        now = datetime.now()
        previous_entries = filter_entries_between(
            entries,
            start_inclusive=now - timedelta(days=2 * days),
            end_exclusive=now - timedelta(days=days),
            include_missing_timestamp=False,
        )
        previous_summary = summarize_by_source(previous_entries)

    ai_summary = ""
    if "--ai" in args:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                ai_summary = generate_ai_summary(filtered_entries, api_key=api_key)
            except Exception as e:
                print(f"AI API error ({type(e).__name__}). Using local fallback summary.")
                ai_summary = generate_fallback_summary(filtered_entries)
        else:
            ai_summary = generate_fallback_summary(filtered_entries)

    report_path = write_weekly_report(
        filtered_entries,
        summary,
        ai_summary=ai_summary,
        previous_summary=previous_summary,
        period_days=days if days > 0 else None,
    )
    append_activity("weekly_report", {"report_path": str(report_path), "used_ai": "--ai" in args, "days": days})
    print(f"Updated: {report_path}")


def handle_monthly_report(args: list[str]) -> None:
    entries = load_entries()

    target_month = datetime.now().strftime("%Y-%m")
    if "--month" in args:
        idx = args.index("--month")
        if idx + 1 < len(args):
            target_month = args[idx + 1]

    try:
        month_start = datetime.strptime(target_month, "%Y-%m")
    except ValueError:
        print("Invalid --month value. Use YYYY-MM format.")
        return

    if month_start.month == 12:
        next_month = datetime(month_start.year + 1, 1, 1)
    else:
        next_month = datetime(month_start.year, month_start.month + 1, 1)

    if month_start.month == 1:
        previous_month_start = datetime(month_start.year - 1, 12, 1)
    else:
        previous_month_start = datetime(month_start.year, month_start.month - 1, 1)

    filtered_entries = filter_entries_between(
        entries,
        start_inclusive=month_start,
        end_exclusive=next_month,
        include_missing_timestamp=False,
    )
    summary = summarize_by_source(filtered_entries)

    previous_entries = filter_entries_between(
        entries,
        start_inclusive=previous_month_start,
        end_exclusive=month_start,
        include_missing_timestamp=False,
    )
    previous_summary = summarize_by_source(previous_entries)

    ai_summary = ""
    if "--ai" in args:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                ai_summary = generate_ai_summary(filtered_entries, api_key=api_key)
            except Exception as e:
                print(f"AI API error ({type(e).__name__}). Using local fallback summary.")
                ai_summary = generate_fallback_summary(filtered_entries)
        else:
            ai_summary = generate_fallback_summary(filtered_entries)

    report_path = write_monthly_report(
        filtered_entries,
        summary,
        ai_summary=ai_summary,
        previous_summary=previous_summary,
        month_label=target_month,
    )
    append_activity("monthly_report", {"report_path": str(report_path), "used_ai": "--ai" in args, "month": target_month})
    print(f"Updated: {report_path}")


def handle_retention(_: list[str]) -> None:
    result = run_retention()
    print("Retention completed.")
    print(f"RETENTION_DAYS={result['retention_days']}")
    print(f"collected_data: moved={result['collected_data']['moved']} kept={result['collected_data']['kept']}")
    print(f"activity_history: moved={result['activity_history']['moved']} kept={result['activity_history']['kept']}")
    print(f"alerts: moved={result['alerts']['moved']} kept={result['alerts']['kept']}")
    print(f"metrics: moved={result['metrics']['moved']} kept={result['metrics']['kept']}")
    print(f"total: moved={result['total']['moved']} kept={result['total']['kept']}")
    append_activity(
        "retention",
        {
            "retention_days": result["retention_days"],
            "moved": result["total"]["moved"],
            "kept": result["total"]["kept"],
        },
    )


def handle_metrics_summary(args: list[str]) -> None:
    days = 30
    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                days = int(args[idx + 1])
            except ValueError:
                days = 30

    summary = build_metrics_summary(days=days)

    if "--json" in args:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(format_metrics_summary_text(summary))


def handle_metrics_check(args: list[str]) -> bool:
    days = 30
    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                days = int(args[idx + 1])
            except ValueError:
                days = 30

    result = check_metric_thresholds(days=days)
    violations = result.get("violations", [])
    threshold_profile = str(result.get("threshold_profile", "prod"))
    continuous_alert = result.get("continuous_alert", {}) if isinstance(result.get("continuous_alert"), dict) else {}
    continuous_severity = str(continuous_alert.get("severity", "none")).strip().lower()
    if continuous_severity not in {"none", "warning", "critical"}:
        continuous_severity = "none"

    if "--json" in args:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "days": days,
                    "threshold_profile": threshold_profile,
                    "violations": violations,
                    "continuous_alert": continuous_alert,
                },
                ensure_ascii=False,
            )
        )
    else:
        print(f"Metric threshold profile: {threshold_profile}")
        warning_limit = int(continuous_alert.get("warning_limit", continuous_alert.get("limit", 0)))
        critical_limit = int(continuous_alert.get("critical_limit", warning_limit))
        continuous_active = bool(continuous_alert.get("active", False))
        print(
            "Continuous SLO alert severity: "
            f"{continuous_severity} (warning_limit={warning_limit}, critical_limit={critical_limit})"
        )
        print(f"Continuous SLO alert active: {str(continuous_active).lower()}")
        if continuous_active:
            continuous_rows = continuous_alert.get("violated_pipelines", [])
            if isinstance(continuous_rows, list):
                print("Continuous SLO breached pipelines:")
                for row in continuous_rows:
                    if not isinstance(row, dict):
                        continue
                    pipeline = str(row.get("pipeline", "unknown"))
                    consecutive = int(row.get("consecutive_failures", 0))
                    latest_run = str(row.get("latest_run", ""))
                    pipeline_severity = str(row.get("severity", "warning"))
                    print(
                        "- pipeline="
                        f"{pipeline} severity={pipeline_severity} consecutive_failures={consecutive} latest_run={latest_run}"
                    )
        if violations:
            print(f"Metric threshold violations ({len(violations)}):")
            for item in violations:
                pipeline = item.get("pipeline", "unknown")
                metric = item.get("metric", "unknown")
                threshold = float(item.get("threshold", 0.0))
                observed = float(item.get("observed", 0.0))
                print(f"- pipeline={pipeline} metric={metric} threshold={threshold:.6g} observed={observed:.6g}")
        else:
            print("No metric threshold violations.")

    return bool(violations) or continuous_severity == "critical"


def handle_ops_report(args: list[str]) -> None:
    days = 7
    emit_json = "--json" in args
    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                days = max(0, int(args[idx + 1]))
            except ValueError:
                days = 7

    report, report_path = generate_and_write_ops_report(days=days)
    append_activity(
        "ops_report",
        {
            "report_path": str(report_path),
            "days": days,
            "threshold_violations": int(report.get("threshold_violations_count", 0)),
            "command_failures": int(report.get("recent_command_failures", 0)),
        },
    )
    if emit_json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"Updated: {report_path}")


def handle_ops_report_index(args: list[str]) -> None:
    limit = 8
    if "--limit" in args:
        idx = args.index("--limit")
        if idx + 1 < len(args):
            try:
                limit = max(1, int(args[idx + 1]))
            except ValueError:
                limit = 8

    index_path = write_ops_reports_index(limit=limit)
    append_activity("ops_report_index", {"index_path": str(index_path), "limit": limit})
    print(f"Updated: {index_path}")


def handle_alert_dedup_status(args: list[str]) -> None:
    emit_json = "--json" in args
    state_path = DEFAULT_ALERT_DEDUP_STATE_PATH
    top_n = 5

    if "--state-path" in args:
        idx = args.index("--state-path")
        if idx + 1 < len(args):
            state_path = Path(args[idx + 1])

    if "--top" in args:
        idx = args.index("--top")
        if idx + 1 < len(args):
            try:
                top_n = max(0, int(args[idx + 1]))
            except ValueError:
                top_n = 5

    summary = summarize_alert_dedup_state(state_path, top_n=top_n)
    if emit_json:
        print(json.dumps(summary, ensure_ascii=False))
        return

    print(f"Alert dedup state: {summary['state_path']}")
    print(f"Entry count: {summary['entry_count']}")
    print(f"Oldest timestamp: {summary.get('oldest_timestamp') or '-'}")
    print(f"Newest timestamp: {summary.get('newest_timestamp') or '-'}")

    top_signatures = summary.get("top_signatures", [])
    if isinstance(top_signatures, list) and top_signatures:
        print("Top signatures:")
        for row in top_signatures:
            if not isinstance(row, dict):
                continue
            signature_preview = str(row.get("signature_preview") or "")
            timestamp = str(row.get("timestamp") or "-")
            print(f"- {signature_preview} @ {timestamp}")
    else:
        print("Top signatures: (none)")


def handle_alert_dedup_reset(args: list[str]) -> None:
    emit_json = "--json" in args
    backup = "--backup" in args
    state_path = DEFAULT_ALERT_DEDUP_STATE_PATH

    if "--state-path" in args:
        idx = args.index("--state-path")
        if idx + 1 < len(args):
            state_path = Path(args[idx + 1])

    result = reset_alert_dedup_state(state_path, backup=backup)
    if emit_json:
        print(json.dumps(result, ensure_ascii=False))
        return

    print("Alert dedup state reset completed.")
    print(f"State file: {result['state_path']}")
    print(f"Entries before: {result['entry_count_before']}")
    print(f"Entries after: {result['entry_count_after']}")
    if result.get("backup_path"):
        print(f"Backup: {result['backup_path']}")
    elif not result.get("existed"):
        print("State file did not exist; initialized empty state.")


def handle_alert_dedup_prune(args: list[str]) -> None:
    emit_json = "--json" in args
    state_path = DEFAULT_ALERT_DEDUP_STATE_PATH
    ttl_sec: int | None = None

    if "--state-path" in args:
        idx = args.index("--state-path")
        if idx + 1 < len(args):
            state_path = Path(args[idx + 1])

    if "--ttl-sec" in args:
        idx = args.index("--ttl-sec")
        if idx + 1 < len(args):
            try:
                ttl_sec = max(0, int(args[idx + 1]))
            except ValueError:
                ttl_sec = None

    result = prune_alert_dedup_state(state_path, ttl_sec=ttl_sec)
    if emit_json:
        print(json.dumps(result, ensure_ascii=False))
        return

    print("Alert dedup prune completed.")
    print(f"State file: {result['state_path']}")
    print(f"TTL sec: {result['ttl_sec']}")
    print(f"Entries before: {result['entry_count_before']}")
    print(f"Entries after: {result['entry_count_after']}")
    print(f"Removed: {result['removed_count']}")


def main():
    def print_main_usage() -> None:
        print("Usage: python -m src.main <command> [options]")
        print(
            "Commands: collect, analyze, fetch, apply-insights, weekly-report, monthly-report, "
            "retention, metrics-summary, metrics-check, ops-report, ops-report-index, "
            "alert-dedup-status, alert-dedup-reset, alert-dedup-prune, doctor, env-init"
        )

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd in {"-h", "--help", "help"}:
            print_main_usage()
            return
        if cmd == "collect":
            handle_collect(sys.argv[2:])
            return
        elif cmd == "analyze":
            handle_analyze(sys.argv[2:])
            return
        elif cmd == "fetch":
            handle_fetch(sys.argv[2:])
            return
        elif cmd == "apply-insights":
            handle_apply_insights(sys.argv[2:])
            return
        elif cmd == "weekly-report":
            handle_weekly_report(sys.argv[2:])
            return
        elif cmd == "monthly-report":
            handle_monthly_report(sys.argv[2:])
            return
        elif cmd in {"retention", "retention-run"}:
            handle_retention(sys.argv[2:])
            return
        elif cmd == "metrics-summary":
            handle_metrics_summary(sys.argv[2:])
            return
        elif cmd == "metrics-check":
            has_violations = handle_metrics_check(sys.argv[2:])
            if has_violations:
                raise SystemExit(1)
            return
        elif cmd == "ops-report":
            handle_ops_report(sys.argv[2:])
            return
        elif cmd == "ops-report-index":
            handle_ops_report_index(sys.argv[2:])
            return
        elif cmd == "alert-dedup-status":
            handle_alert_dedup_status(sys.argv[2:])
            return
        elif cmd == "alert-dedup-reset":
            handle_alert_dedup_reset(sys.argv[2:])
            return
        elif cmd == "alert-dedup-prune":
            handle_alert_dedup_prune(sys.argv[2:])
            return
        elif cmd == "doctor":
            if "--json" in sys.argv[2:]:
                print_doctor_report_json()
            else:
                print_doctor_report()
            return
        elif cmd == "env-init":
            result = ensure_env_from_example()
            if result["missing_example"]:
                print(".env.example not found.")
            else:
                print(f".env initialized. created={result['created']} added={result['added']}")
            return

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print_main_usage()
        print("Please set OPENAI_API_KEY environment variable.")
        return

    print_main_usage()
    print("Tip: run a concrete command above. OPENAI_API_KEY is configured.")


if __name__ == "__main__":
    main()

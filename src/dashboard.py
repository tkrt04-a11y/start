"""Streamlit dashboard for collection and analysis workflow."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re

import streamlit as st

from src.collector import DataCollector
from src.analyzer import load_entries, summarize_by_source, generate_ai_summary, generate_fallback_summary
from src.connectors import fetch_github_issues, fetch_rss_feed, fetch_survey_json
from src.reflector import write_backlog
from src.reporter import write_weekly_report, write_monthly_report, filter_entries_by_days, filter_entries_between
from src.activity_log import append_activity, read_recent_activities
from src.alert_dedup import load_alert_dedup_state
from src.alerts import ALERT_TYPE_CATEGORIES, PIPELINE_CATEGORIES, parse_alert_lines, summarize_alerts
from src.metrics import check_metric_thresholds


ALERT_TYPE_LABELS = {
    "threshold": "しきい値",
    "webhook_failed": "Webhook失敗",
    "command_failed": "コマンド失敗",
    "monthly_scheduled": "月次スケジュール",
    "other": "その他",
}

PIPELINE_LABELS = {
    "daily": "日次",
    "weekly": "週次",
    "monthly": "月次",
    "unknown": "不明",
}

SLO_DEFAULT_TARGETS = {
    "daily": 95.0,
    "weekly": 90.0,
    "monthly": 90.0,
}


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _extract_first_int(value: str) -> int:
    matched = re.search(r"-?\d+", value)
    if not matched:
        return 0
    return int(matched.group(0))


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.replace(tzinfo=None)
    return parsed


def _collect_release_ci_health(logs_dir: Path, releases_dir: Path) -> dict[str, object]:
    latest_release = {
        "name": "N/A",
        "updated_at": "",
    }

    release_candidates = sorted(releases_dir.glob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in release_candidates:
        text = _safe_read_text(path)
        heading = ""
        for line in text.splitlines():
            candidate = line.strip()
            if candidate.startswith("# "):
                heading = candidate[2:].strip()
                break
        latest_release = {
            "name": heading or path.stem,
            "updated_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }
        break

    workflow_rows: list[dict[str, object]] = []
    for pipeline in ["daily", "weekly", "monthly"]:
        latest_path: Path | None = None
        latest_time = datetime.min
        for path in logs_dir.glob(f"{pipeline}-metrics-*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            finished_text = str(payload.get("finished_at") or payload.get("started_at") or "")
            finished_dt = _parse_timestamp(finished_text)
            if finished_dt is None:
                continue
            if finished_dt >= latest_time:
                latest_time = finished_dt
                latest_path = path

        if latest_path is None:
            workflow_rows.append(
                {
                    "workflow": PIPELINE_LABELS.get(pipeline, pipeline),
                    "latest_status": "UNKNOWN",
                    "finished_at": "",
                }
            )
            continue

        try:
            latest_payload = json.loads(latest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            latest_payload = {}

        workflow_rows.append(
            {
                "workflow": PIPELINE_LABELS.get(pipeline, pipeline),
                "latest_status": "SUCCESS" if bool(latest_payload.get("success", False)) else "FAILED",
                "finished_at": str(latest_payload.get("finished_at", "")),
            }
        )

    failure_reason_counts: dict[str, int] = {}
    diagnostic_path = logs_dir / "weekly-ops-failure-diagnostic.md"
    if diagnostic_path.exists():
        parsed = _parse_weekly_failure_diagnostic_markdown(_safe_read_text(diagnostic_path))
        reasons = parsed.get("failure_reasons", [])
        if isinstance(reasons, list):
            for reason in reasons:
                reason_text = str(reason).strip()
                if not reason_text:
                    continue
                failure_reason_counts[reason_text] = failure_reason_counts.get(reason_text, 0) + 1

    top_failure_reasons = [
        {"reason": key, "count": count}
        for key, count in sorted(failure_reason_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    ]

    return {
        "latest_release": latest_release,
        "workflow_rows": workflow_rows,
        "top_failure_reasons": top_failure_reasons,
    }


def _parse_ops_report_markdown(text: str) -> dict[str, object]:
    if not text.strip():
        return {}

    parsed: dict[str, object] = {
        "days": 0,
        "total_runs": 0,
        "total_violations": 0,
        "recent_command_failures": 0,
        "artifact_integrity_ok": 0,
        "artifact_integrity_missing": 0,
        "artifact_integrity_total": 0,
        "pipeline_rows": [],
        "top_alert_rows": [],
        "daily_alert_summary_rows": [],
        "artifact_integrity_rows": [],
    }

    current_section = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            current_section = line
            continue

        if line.startswith("- Days:"):
            parsed["days"] = _extract_first_int(line)
            continue
        if line.startswith("- Total runs:"):
            parsed["total_runs"] = _extract_first_int(line)
            continue
        if line.startswith("- Total violations:"):
            parsed["total_violations"] = _extract_first_int(line)
            continue
        if line.startswith("- Recent command failures:"):
            parsed["recent_command_failures"] = _extract_first_int(line)
            continue

        if current_section == "## Artifact Integrity" and line.startswith("- Summary:"):
            summary_match = re.match(r"^-\s*Summary:\s*ok=(-?\d+),\s*missing=(-?\d+),\s*total=(-?\d+)\s*$", line)
            if summary_match:
                parsed["artifact_integrity_ok"] = int(summary_match.group(1))
                parsed["artifact_integrity_missing"] = int(summary_match.group(2))
                parsed["artifact_integrity_total"] = int(summary_match.group(3))
            continue

        if current_section == "## Artifact Integrity" and line.startswith("- "):
            check_match = re.match(r"^-\s*\[(OK|MISSING)\]\s+(.+)\s*$", line)
            if check_match:
                rows = parsed["artifact_integrity_rows"]
                if isinstance(rows, list):
                    rows.append({"status": check_match.group(1), "path": check_match.group(2).strip()})
            continue

        if current_section == "## Pipeline Success Rate" and line.startswith("- "):
            matched = re.match(r"^-\s*([^:]+):\s*runs=(\d+),\s*success_rate=([\d.]+)%\s*$", line)
            if matched:
                pipeline_rows = parsed["pipeline_rows"]
                if isinstance(pipeline_rows, list):
                    pipeline_rows.append(
                        {
                            "pipeline": matched.group(1),
                            "runs": int(matched.group(2)),
                            "success_rate(%)": float(matched.group(3)),
                        }
                    )
            continue

        if current_section == "## Top Alert Types" and line.startswith("- "):
            matched = re.match(r"^-\s*([^:]+):\s*(-?\d+)\s*$", line)
            if matched:
                alert_rows = parsed["top_alert_rows"]
                if isinstance(alert_rows, list):
                    alert_rows.append({"type": matched.group(1), "count": int(matched.group(2))})

        if current_section == "## Daily Alert Summaries" and line.startswith("- "):
            matched = re.match(
                r"^-\s*(\d{4}-\d{2}-\d{2}):\s*command_failures=(-?\d+),\s*alert_count=(-?\d+)\s*$",
                line,
            )
            if matched:
                daily_rows = parsed["daily_alert_summary_rows"]
                if isinstance(daily_rows, list):
                    daily_rows.append(
                        {
                            "date": matched.group(1),
                            "command_failures": int(matched.group(2)),
                            "alert_count": int(matched.group(3)),
                        }
                    )

    return parsed


def _parse_weekly_failure_diagnostic_markdown(text: str) -> dict[str, object]:
    if not text.strip():
        return {}

    parsed: dict[str, object] = {
        "generated_at": "",
        "failure_reasons": [],
        "reproduction_commands": [],
        "required_file_checks": [],
    }

    current_section = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            current_section = line
            continue

        if line.startswith("- Generated at (UTC):"):
            parsed["generated_at"] = line.split(":", 1)[1].strip()
            continue

        if current_section == "## Failure Reasons" and line.startswith("- "):
            reasons = parsed["failure_reasons"]
            if isinstance(reasons, list):
                reasons.append(line[2:].strip())
            continue

        if current_section == "## Reproduction Commands" and line.startswith("- "):
            commands = parsed["reproduction_commands"]
            if isinstance(commands, list):
                commands.append(line[2:].strip())
            continue

        if current_section == "## Required File Verification" and line.startswith("- "):
            matched = re.match(r"^-\s*\[(OK|MISSING)\]\s+(.+)\s*$", line)
            if matched:
                checks = parsed["required_file_checks"]
                if isinstance(checks, list):
                    checks.append({"status": matched.group(1), "path": matched.group(2).strip()})

    return parsed


def _load_daily_alert_summaries_from_logs(logs_dir: Path, limit: int = 7) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(logs_dir.glob("alerts-summary-*.md"), reverse=True):
        matched = re.match(r"^alerts-summary-(\d{8})$", path.stem)
        if not matched:
            continue

        text = _safe_read_text(path)
        if not text.strip():
            continue

        command_failures = 0
        alert_count = 0
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("- Command failures:"):
                command_failures = _extract_first_int(line)
            elif line.startswith("- Alert count:"):
                alert_count = _extract_first_int(line)

        date_text = matched.group(1)
        rows.append(
            {
                "date": f"{date_text[0:4]}-{date_text[4:6]}-{date_text[6:8]}",
                "command_failures": command_failures,
                "alert_count": alert_count,
            }
        )

        if len(rows) >= limit:
            break

    return rows


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _build_pipeline_slo_rows(
    summary: dict[str, object],
    targets: dict[str, float] | None = None,
) -> list[dict[str, object]]:
    resolved_targets = targets or SLO_DEFAULT_TARGETS
    pipelines = summary.get("pipelines", {}) if isinstance(summary.get("pipelines"), dict) else {}
    rows: list[dict[str, object]] = []

    for pipeline_name in sorted(pipelines.keys()):
        pipeline_payload = pipelines.get(pipeline_name, {})
        if not isinstance(pipeline_payload, dict):
            continue

        runs = _safe_int(pipeline_payload.get("runs", 0))
        observed = float(pipeline_payload.get("success_rate", 0.0)) * 100.0
        target = float(resolved_targets.get(pipeline_name, 90.0))
        gap = observed - target
        rows.append(
            {
                "pipeline": PIPELINE_LABELS.get(pipeline_name, pipeline_name),
                "runs": runs,
                "slo_target(%)": round(target, 1),
                "observed_success(%)": round(observed, 1),
                "gap(%)": round(gap, 1),
                "status": "PASS" if observed >= target else "FAIL",
            }
        )
    return rows


def _build_kpi_trend_rows(
    recent_result: dict[str, object],
    baseline_result: dict[str, object],
) -> list[dict[str, object]]:
    def _extract_kpis(result: dict[str, object]) -> dict[str, float]:
        health = result.get("health", {}) if isinstance(result.get("health"), dict) else {}
        health_factors = health.get("factors", {}) if isinstance(health.get("factors"), dict) else {}
        violations = result.get("violations", []) if isinstance(result.get("violations"), list) else []
        return {
            "health_score": float(_safe_int(health.get("score", 0))),
            "violations": float(len(violations)),
            "command_failures": float(_safe_int(health_factors.get("command_failures", 0))),
            "alerts": float(_safe_int(health_factors.get("alert_count", 0))),
        }

    recent = _extract_kpis(recent_result)
    baseline = _extract_kpis(baseline_result)
    specs = [
        ("Health score", "health_score", True),
        ("Violations", "violations", False),
        ("Command failures", "command_failures", False),
        ("Alerts", "alerts", False),
    ]

    rows: list[dict[str, object]] = []
    for label, key, higher_is_better in specs:
        recent_value = recent.get(key, 0.0)
        baseline_value = baseline.get(key, 0.0)
        delta = recent_value - baseline_value
        if abs(delta) < 1e-9:
            trend = "同等"
        elif (delta > 0 and higher_is_better) or (delta < 0 and not higher_is_better):
            trend = "改善"
        else:
            trend = "悪化"

        rows.append(
            {
                "kpi": label,
                "7d": round(recent_value, 1),
                "30d": round(baseline_value, 1),
                "delta(7d-30d)": round(delta, 1),
                "trend": trend,
            }
        )

    return rows


def _read_recent_jsonl_records(path: Path, limit: int = 2000) -> list[dict[str, object]]:
    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    rows: list[dict[str, object]] = []
    for line in lines[-limit:]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _collect_issue_sync_stats(logs_dir: Path) -> dict[str, object]:
    created = 0
    failed = 0
    retries = 0
    retry_observed = False

    activity_records: list[dict[str, object]] = []
    activity_paths: list[Path] = []
    for candidate in [logs_dir / "activity_history.jsonl", logs_dir / "activity_log.jsonl"]:
        if candidate.exists():
            activity_paths.append(candidate)
            activity_records.extend(_read_recent_jsonl_records(candidate, limit=2000))

    activity_found = False
    for record in activity_records:
        event = str(record.get("event", "")).strip().lower()
        details = record.get("details", {})
        if not isinstance(details, dict):
            details = {}

        if event == "apply_insights":
            has_issue_sync_fields = any(
                key in details for key in ["issue_sync_created", "issue_sync_failed", "issue_sync_retries"]
            )
            if not has_issue_sync_fields:
                continue
            activity_found = True
            created += _safe_int(details.get("issue_sync_created", 0))
            failed += _safe_int(details.get("issue_sync_failed", 0))
            if "issue_sync_retries" in details:
                retry_observed = True
                retries += _safe_int(details.get("issue_sync_retries", 0))
            continue

        if event in {"issue_sync", "issue_sync_result"}:
            activity_found = True
            created += _safe_int(details.get("created", 0))
            failed += _safe_int(details.get("failed", 0))
            if "retries" in details:
                retry_observed = True
                retries += _safe_int(details.get("retries", 0))

    if activity_found:
        source = ", ".join(path.name for path in activity_paths) if activity_paths else "activity"
        return {
            "success": created,
            "failure": failed,
            "retries": retries if retry_observed else None,
            "source": source,
        }

    created_pattern = re.compile(r"Issue sync:\s*created=(\d+)\s+skipped_existing=(\d+)", re.IGNORECASE)
    issue_sync_found = False
    for path in sorted(logs_dir.glob("*-run-*.log"), reverse=True)[:20]:
        text = _safe_read_text(path)
        if not text.strip():
            continue

        for raw_line in text.splitlines():
            line = raw_line.strip()
            matched = created_pattern.search(line)
            if matched:
                issue_sync_found = True
                retry_observed = True
                created += _safe_int(matched.group(1))
                continue

            normalized = line.lower()
            if "issue sync skipped:" in normalized or "issue sync failed:" in normalized:
                issue_sync_found = True
                retry_observed = True
                failed += 1
                continue

            if "issue sync" in normalized and "retrying" in normalized:
                issue_sync_found = True
                retry_observed = True
                retries += 1

    if issue_sync_found:
        return {
            "success": created,
            "failure": failed,
            "retries": retries if retry_observed else None,
            "source": "*-run-*.log",
        }

    return {"success": 0, "failure": 0, "retries": None, "source": "N/A"}


def main() -> None:
    st.set_page_config(page_title="AI Starter Kit Dashboard", layout="wide")
    st.title("AI駆動開発スターターキット ダッシュボード")

    collector = DataCollector()

    tab_collect, tab_analyze, tab_fetch, tab_reflect, tab_report, tab_history, tab_alerts, tab_metrics = st.tabs(
        ["Collect", "Analyze", "Fetch", "Reflect", "Weekly Report", "History", "Alerts", "Metrics"]
    )

    with tab_collect:
        st.subheader("手動収集")
        source = st.text_input("Source", value="manual")
        content = st.text_area("Content")
        if st.button("保存", key="collect_save"):
            if content.strip():
                collector.collect(source.strip() or "manual", content.strip())
                append_activity("dashboard_collect", {"source": source.strip() or "manual", "content_preview": content.strip()[:120]})
                st.success("保存しました")
            else:
                st.warning("Content を入力してください")

    with tab_analyze:
        st.subheader("分析")
        entries = load_entries()
        summary = summarize_by_source(entries)
        st.write("件数:", len(entries))
        if summary:
            st.bar_chart(summary)
        else:
            st.info("まだデータがありません")

        use_ai = st.checkbox("AI要約を生成")
        model = st.text_input("Model", value="gpt-4o-mini")
        if st.button("分析実行", key="analyze_run"):
            st.write("### Source Summary")
            st.json(summary)
            append_activity("dashboard_analyze", {"entry_count": len(entries), "use_ai": use_ai})
            if use_ai:
                api_key = os.getenv("OPENAI_API_KEY", "")
                if not api_key:
                    st.error("OPENAI_API_KEY が未設定です")
                else:
                    with st.spinner("AI要約を生成中..."):
                        try:
                            ai_text = generate_ai_summary(entries, api_key=api_key, model=model)
                        except Exception as e:
                            st.warning(f"AI APIエラー（{type(e).__name__}）。ローカル要約に切り替えます。")
                            ai_text = generate_fallback_summary(entries)
                    st.write("### AI Summary")
                    st.write(ai_text)

    with tab_fetch:
        st.subheader("自動収集コネクタ")
        connector = st.selectbox("Connector", ["github", "rss", "survey-json"])

        if connector == "github":
            repo = st.text_input("repo (owner/name)", value="microsoft/vscode")
            state = st.selectbox("state", ["open", "closed", "all"])
            limit = st.number_input("limit", min_value=1, max_value=100, value=20)
            if st.button("GitHubから取得"):
                items = fetch_github_issues(repo, state=state, limit=int(limit))
                for item in items:
                    collector.collect(item["source"], item["content"])
                append_activity("dashboard_fetch", {"connector": "github", "fetched_count": len(items), "repo": repo})
                st.success(f"{len(items)} 件取り込みました")

        elif connector == "rss":
            feed = st.text_input("feed url", value="https://hnrss.org/frontpage")
            limit = st.number_input("limit", min_value=1, max_value=100, value=20, key="rss_limit")
            if st.button("RSSから取得"):
                items = fetch_rss_feed(feed, limit=int(limit))
                for item in items:
                    collector.collect(item["source"], item["content"])
                append_activity("dashboard_fetch", {"connector": "rss", "fetched_count": len(items), "feed": feed})
                st.success(f"{len(items)} 件取り込みました")

        else:
            path = st.text_input("json path", value="survey.json")
            field = st.text_input("content field", value="content")
            if st.button("Survey JSONから取得"):
                items = fetch_survey_json(path, content_field=field)
                for item in items:
                    collector.collect(item["source"], item["content"])
                append_activity("dashboard_fetch", {"connector": "survey-json", "fetched_count": len(items), "path": path})
                st.success(f"{len(items)} 件取り込みました")

    with tab_reflect:
        st.subheader("反映")
        if st.button("改善バックログを生成"):
            entries = load_entries()
            summary = summarize_by_source(entries)
            output = write_backlog(summary)
            append_activity("dashboard_reflect", {"output": str(output)})
            st.success(f"生成: {output}")

    with tab_report:
        st.subheader("週次レポート")
        use_ai = st.checkbox("AI/ヒューリスティック要約を含める", value=True, key="weekly_use_ai")
        days = st.number_input("対象日数（0 = 全期間）", min_value=0, max_value=3650, value=7, step=1)
        if st.button("週次レポートを生成"):
            entries = load_entries()
            filtered_entries = filter_entries_by_days(entries, days=int(days))
            summary = summarize_by_source(filtered_entries)

            previous_summary: dict[str, int] | None = None
            if int(days) > 0:
                now = datetime.now()
                previous_entries = filter_entries_between(
                    entries,
                    start_inclusive=now - timedelta(days=2 * int(days)),
                    end_exclusive=now - timedelta(days=int(days)),
                    include_missing_timestamp=False,
                )
                previous_summary = summarize_by_source(previous_entries)

            ai_summary = ""
            if use_ai:
                api_key = os.getenv("OPENAI_API_KEY", "")
                if api_key:
                    try:
                        ai_summary = generate_ai_summary(filtered_entries, api_key=api_key)
                    except Exception as e:
                        st.warning(f"AI APIエラー（{type(e).__name__}）。ローカル要約に切り替えます。")
                        ai_summary = generate_fallback_summary(filtered_entries)
                else:
                    ai_summary = generate_fallback_summary(filtered_entries)

            output = write_weekly_report(
                filtered_entries,
                summary,
                ai_summary=ai_summary,
                previous_summary=previous_summary,
                period_days=int(days) if int(days) > 0 else None,
            )
            append_activity("dashboard_weekly_report", {"output": str(output), "use_ai": use_ai, "days": int(days)})
            st.success(f"生成: {output}")

        st.markdown("### 月次レポート")
        month_text = st.text_input("対象月（YYYY-MM）", value=datetime.now().strftime("%Y-%m"), key="monthly_month")
        if st.button("月次レポートを生成"):
            try:
                month_start = datetime.strptime(month_text, "%Y-%m")
            except ValueError:
                st.error("対象月は YYYY-MM 形式で入力してください")
            else:
                if month_start.month == 12:
                    next_month = datetime(month_start.year + 1, 1, 1)
                else:
                    next_month = datetime(month_start.year, month_start.month + 1, 1)

                entries = load_entries()
                filtered_entries = filter_entries_between(
                    entries,
                    start_inclusive=month_start,
                    end_exclusive=next_month,
                    include_missing_timestamp=False,
                )
                summary = summarize_by_source(filtered_entries)

                ai_summary = ""
                if use_ai:
                    api_key = os.getenv("OPENAI_API_KEY", "")
                    if api_key:
                        try:
                            ai_summary = generate_ai_summary(filtered_entries, api_key=api_key)
                        except Exception as e:
                            st.warning(f"AI APIエラー（{type(e).__name__}）。ローカル要約に切り替えます。")
                            ai_summary = generate_fallback_summary(filtered_entries)
                    else:
                        ai_summary = generate_fallback_summary(filtered_entries)

                output = write_monthly_report(
                    filtered_entries,
                    summary,
                    ai_summary=ai_summary,
                    month_label=month_text,
                )
                append_activity("dashboard_monthly_report", {"output": str(output), "use_ai": use_ai, "month": month_text})
                st.success(f"生成: {output}")

    with tab_history:
        st.subheader("時刻付き操作履歴")
        limit = st.number_input("表示件数", min_value=10, max_value=1000, value=100, step=10)
        records = read_recent_activities(limit=int(limit))
        if not records:
            st.info("履歴はまだありません")
        else:
            st.dataframe(records, use_container_width=True)

    with tab_alerts:
        st.subheader("アラート監視")
        alert_path = Path("logs/alerts.log")
        dedup_state_count = len(load_alert_dedup_state(Path("logs/alert_dedup_state.json")))
        st.metric("Dedupシグネチャ数", dedup_state_count)
        if not alert_path.exists():
            st.info("alerts.log はまだ作成されていません")
        else:
            lines = [line for line in alert_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            st.metric("総アラート件数", len(lines))
            period_days = st.number_input("集計日数", min_value=1, max_value=365, value=30, step=1, key="alerts_days")

            now = datetime.now()
            parsed_alerts = parse_alert_lines(lines)
            per_day, pipeline_counts, type_counts = summarize_alerts(
                parsed_alerts,
                since=now - timedelta(days=int(period_days)),
            )

            if per_day:
                st.bar_chart(dict(sorted(per_day.items())), use_container_width=True)
            else:
                st.info("指定期間のアラートはありません")

            st.write("### パイプライン内訳（指定期間）")
            pipeline_rows = [
                {"pipeline": PIPELINE_LABELS.get(name, name), "count": pipeline_counts.get(name, 0)}
                for name in PIPELINE_CATEGORIES
            ]
            st.table(pipeline_rows)
            non_zero_pipeline = {
                PIPELINE_LABELS.get(name, name): count for name, count in pipeline_counts.items() if count > 0
            }
            if non_zero_pipeline:
                st.bar_chart(non_zero_pipeline, use_container_width=True)

            st.write("### 種別内訳（指定期間）")
            type_rows = [
                {"type": ALERT_TYPE_LABELS.get(name, name), "count": type_counts.get(name, 0)}
                for name in ALERT_TYPE_CATEGORIES
            ]
            st.table(type_rows)
            non_zero_types = {
                ALERT_TYPE_LABELS.get(name, name): count for name, count in type_counts.items() if count > 0
            }
            if non_zero_types:
                st.bar_chart(non_zero_types, use_container_width=True)

            recent_limit = st.number_input("直近表示件数", min_value=10, max_value=500, value=50, step=10, key="alerts_limit")
            st.code("\n".join(lines[-int(recent_limit):]), language="text")

    with tab_metrics:
        st.subheader("パイプラインメトリクス")
        metrics_days = st.number_input("対象日数（0 = 全期間）", min_value=0, max_value=3650, value=30, step=1, key="metrics_days")
        st.button("更新", key="metrics_refresh")

        st.write("### Release / CI 健全性")
        release_ci = _collect_release_ci_health(Path("logs"), Path("docs/releases"))
        latest_release = release_ci.get("latest_release", {}) if isinstance(release_ci.get("latest_release"), dict) else {}
        release_col1, release_col2 = st.columns(2)
        release_col1.metric("Latest release", str(latest_release.get("name", "N/A")))
        release_col2.metric("Release updated", str(latest_release.get("updated_at", "")))

        workflow_rows = release_ci.get("workflow_rows", [])
        if isinstance(workflow_rows, list) and workflow_rows:
            st.write("#### 直近workflow成否")
            st.table(workflow_rows)

        top_failure_reasons = release_ci.get("top_failure_reasons", [])
        if isinstance(top_failure_reasons, list) and top_failure_reasons:
            st.write("#### 失敗要因トップ")
            st.table(top_failure_reasons)
        else:
            st.info("失敗要因データがありません")

        threshold_check = check_metric_thresholds(days=int(metrics_days), logs_dir="logs")
        summary = threshold_check.get("summary", {}) if isinstance(threshold_check.get("summary"), dict) else {}
        health = threshold_check.get("health", {}) if isinstance(threshold_check.get("health"), dict) else {}
        st.write("集計時刻:", summary.get("generated_at", ""))
        st.write("対象実行数:", int(summary.get("total_runs", 0)))

        st.write("### Operational Health")
        health_score = int(health.get("score", 0))
        st.metric("Health score", f"{health_score}/100")

        kpi_recent = check_metric_thresholds(days=7, logs_dir="logs")
        kpi_baseline = check_metric_thresholds(days=30, logs_dir="logs")
        trend_rows = _build_kpi_trend_rows(kpi_recent, kpi_baseline)
        st.write("### KPIトレンド（7日 / 30日）")
        st.table(trend_rows)

        health_factors = health.get("factors", {}) if isinstance(health.get("factors"), dict) else {}
        average_success_rate = float(health_factors.get("average_pipeline_success_rate", 0.0)) * 100.0
        violation_count = int(health_factors.get("violation_count", 0))
        command_failures = int(health_factors.get("command_failures", 0))
        alert_count = int(health_factors.get("alert_count", 0))
        factor_col1, factor_col2, factor_col3, factor_col4 = st.columns(4)
        factor_col1.metric("Avg success(%)", round(average_success_rate, 1))
        factor_col2.metric("Violations", violation_count)
        factor_col3.metric("Command failures", command_failures)
        factor_col4.metric("Alerts", alert_count)

        health_penalties = health.get("penalties", {}) if isinstance(health.get("penalties"), dict) else {}
        st.caption(
            "Penalty breakdown: "
            f"success_rate=-{float(health_penalties.get('success_rate', 0.0)):.1f}, "
            f"violations=-{float(health_penalties.get('violations', 0.0)):.1f}, "
            f"command_failures=-{float(health_penalties.get('command_failures', 0.0)):.1f}, "
            f"alerts=-{float(health_penalties.get('alerts', 0.0)):.1f}"
        )

        totals = summary.get("totals", {}) if isinstance(summary.get("totals"), dict) else {}
        col1, col2 = st.columns(2)
        col1.metric("Total command_failures", int(totals.get("command_failures", 0)))
        col2.metric("Total alert_count", int(totals.get("alert_count", 0)))

        st.write("### Issue Sync 監視")
        issue_sync_stats = _collect_issue_sync_stats(Path("logs"))
        issue_col1, issue_col2, issue_col3 = st.columns(3)
        issue_col1.metric("Success", int(issue_sync_stats.get("success", 0)))
        issue_col2.metric("Failures", int(issue_sync_stats.get("failure", 0)))
        retry_count = issue_sync_stats.get("retries")
        issue_col3.metric("Retries", "N/A" if retry_count is None else int(retry_count))
        st.caption(f"source: {issue_sync_stats.get('source', 'N/A')}")

        st.write("### Weekly Failure Diagnostic（最新）")
        latest_failure_path = Path("logs/weekly-ops-failure-diagnostic.md")
        latest_failure_text = _safe_read_text(latest_failure_path) if latest_failure_path.exists() else ""
        if not latest_failure_text:
            st.info(
                "weekly failure diagnostic が見つかりません。"
                "`logs/weekly-ops-failure-diagnostic.md` 生成後に要約を表示します。"
            )
        else:
            failure_summary = _parse_weekly_failure_diagnostic_markdown(latest_failure_text)
            st.write("生成時刻:", str(failure_summary.get("generated_at", "")))

            failure_reasons = failure_summary.get("failure_reasons", [])
            if isinstance(failure_reasons, list) and failure_reasons:
                st.write("#### 失敗理由")
                st.table([{"reason": str(reason)} for reason in failure_reasons])
            else:
                st.info("失敗理由の記載がありません")

            reproduction_commands = failure_summary.get("reproduction_commands", [])
            if isinstance(reproduction_commands, list) and reproduction_commands:
                st.write("#### 再現コマンド")
                st.table([{"command": str(command)} for command in reproduction_commands])
            else:
                st.info("再現コマンドの記載がありません")

            required_checks = failure_summary.get("required_file_checks", [])
            if isinstance(required_checks, list) and required_checks:
                st.write("#### 必須ファイル検証（要点）")
                missing_paths = [
                    str(item.get("path", ""))
                    for item in required_checks
                    if isinstance(item, dict) and str(item.get("status", "")).upper() == "MISSING"
                ]
                ok_count = len(required_checks) - len(missing_paths)
                check_col1, check_col2 = st.columns(2)
                check_col1.metric("OK", ok_count)
                check_col2.metric("MISSING", len(missing_paths))
                if missing_paths:
                    st.warning("Missing files: " + ", ".join(missing_paths))
                else:
                    st.success("必須ファイルはすべて存在しています")
            else:
                st.info("必須ファイル検証の記載がありません")

        pipelines = summary.get("pipelines", {}) if isinstance(summary.get("pipelines"), dict) else {}
        if not pipelines:
            st.info("指定期間のメトリクスがありません")
        else:
            rows: list[dict[str, object]] = []
            run_counts: dict[str, int] = {}
            success_rates: dict[str, float] = {}
            for name in sorted(pipelines.keys()):
                item = pipelines[name] if isinstance(pipelines[name], dict) else {}
                latest_run = item.get("latest_run", {}) if isinstance(item.get("latest_run"), dict) else {}
                label = PIPELINE_LABELS.get(name, name)
                runs = int(item.get("runs", 0))
                success_rate_pct = float(item.get("success_rate", 0.0)) * 100.0
                rows.append(
                    {
                        "pipeline": label,
                        "runs": runs,
                        "success_rate(%)": round(success_rate_pct, 1),
                        "avg_duration_sec": round(float(item.get("avg_duration_sec", 0.0)), 2),
                        "max_duration_sec": round(float(item.get("max_duration_sec", 0.0)), 2),
                        "latest_run": str(latest_run.get("timestamp", "")),
                        "latest_success": bool(latest_run.get("success", False)),
                    }
                )
                run_counts[label] = runs
                success_rates[label] = success_rate_pct

            st.write("### パイプライン別サマリー")
            st.table(rows)
            st.write("### 実行回数")
            st.bar_chart(run_counts, use_container_width=True)
            st.write("### 成功率（%）")
            st.bar_chart(success_rates, use_container_width=True)

            st.write("### SLO（成功率目標）")
            slo_rows = _build_pipeline_slo_rows(summary)
            if slo_rows:
                st.table(slo_rows)
                failed_rows = [row for row in slo_rows if str(row.get("status")) == "FAIL"]
                if failed_rows:
                    st.warning(
                        "SLO未達: "
                        + ", ".join(str(row.get("pipeline", "")) for row in failed_rows)
                    )
                else:
                    st.success("全パイプラインでSLOを達成しています")

        st.write("### 最近のしきい値違反")
        violations = threshold_check.get("violations", []) if isinstance(threshold_check.get("violations"), list) else []
        thresholds = threshold_check.get("thresholds", {}) if isinstance(threshold_check.get("thresholds"), dict) else {}
        window_start = str(summary.get("window_start") or "-")
        if not violations:
            st.success("選択期間内でしきい値違反は検出されませんでした")
        else:
            violation_rows: list[dict[str, object]] = []
            for violation in violations:
                if not isinstance(violation, dict):
                    continue
                pipeline_name = str(violation.get("pipeline", ""))
                metric_name = str(violation.get("metric", ""))
                observed = float(violation.get("observed", 0.0))
                threshold_value = float(violation.get("threshold", 0.0))
                item = pipelines.get(pipeline_name, {}) if isinstance(pipelines, dict) else {}
                latest_run = item.get("latest_run", {}) if isinstance(item.get("latest_run"), dict) else {}

                if metric_name == "failure_rate":
                    metric_label = "failure_rate(%)"
                    observed_value = round(observed * 100.0, 2)
                    threshold_display = round(
                        float(thresholds.get(pipeline_name, {}).get("max_failure_rate", threshold_value)) * 100.0,
                        2,
                    )
                else:
                    metric_label = "max_duration_sec"
                    observed_value = round(observed, 2)
                    threshold_display = round(
                        float(thresholds.get(pipeline_name, {}).get("max_duration_sec", threshold_value)),
                        2,
                    )

                violation_rows.append(
                    {
                        "pipeline": PIPELINE_LABELS.get(pipeline_name, pipeline_name),
                        "metric": metric_label,
                        "observed": observed_value,
                        "threshold": threshold_display,
                        "latest_run": str(latest_run.get("timestamp", "")),
                        "window_start": window_start,
                    }
                )

            if violation_rows:
                st.table(violation_rows)
            else:
                st.success("選択期間内でしきい値違反は検出されませんでした")

        st.write("### Ops Report（最新）")
        ops_reports_dir = Path("docs/ops_reports")
        latest_ops_md = ops_reports_dir / "latest_ops_report.md"
        latest_text = _safe_read_text(latest_ops_md) if latest_ops_md.exists() else ""
        latest_parsed = _parse_ops_report_markdown(latest_text)

        if not latest_text:
            st.info("最新の ops report が見つかりません。`python -m src.main ops-report` を実行してください。")
        else:
            col_days, col_runs, col_violations, col_failures, col_artifacts = st.columns(5)
            col_days.metric("Days", int(latest_parsed.get("days", 0)))
            col_runs.metric("Total runs", int(latest_parsed.get("total_runs", 0)))
            col_violations.metric("Violations", int(latest_parsed.get("total_violations", 0)))
            col_failures.metric("Cmd failures", int(latest_parsed.get("recent_command_failures", 0)))
            col_artifacts.metric("Missing artifacts", int(latest_parsed.get("artifact_integrity_missing", 0)))

            pipeline_rows = latest_parsed.get("pipeline_rows", [])
            if isinstance(pipeline_rows, list) and pipeline_rows:
                st.write("#### Pipeline Success Rate")
                st.table(pipeline_rows)

            top_alert_rows = latest_parsed.get("top_alert_rows", [])
            if isinstance(top_alert_rows, list) and top_alert_rows:
                st.write("#### Top Alert Types")
                st.table(top_alert_rows)

            daily_alert_rows = latest_parsed.get("daily_alert_summary_rows", [])
            if not isinstance(daily_alert_rows, list) or not daily_alert_rows:
                daily_alert_rows = _load_daily_alert_summaries_from_logs(Path("logs"), limit=7)
            if isinstance(daily_alert_rows, list) and daily_alert_rows:
                st.write("#### Daily Alert Summaries")
                st.table(daily_alert_rows)

            artifact_rows = latest_parsed.get("artifact_integrity_rows", [])
            if isinstance(artifact_rows, list) and artifact_rows:
                st.write("#### Artifact Integrity")
                st.table(artifact_rows)

            st.write("#### 最新レポート本文（Markdown）")
            st.code(latest_text, language="markdown")

        st.write("### Ops Report 履歴")
        history_paths = sorted(ops_reports_dir.glob("ops-report-*.md"), reverse=True)
        if not history_paths:
            st.info("ops report 履歴ファイルがありません")
        else:
            history_labels = [path.name for path in history_paths]
            selected_label = st.selectbox("表示するレポート", history_labels, key="ops_report_history_select")
            selected_path = next((path for path in history_paths if path.name == selected_label), history_paths[0])
            selected_text = _safe_read_text(selected_path)
            st.caption(f"Preview: {selected_path}")
            st.code(selected_text, language="markdown")


if __name__ == "__main__":
    main()

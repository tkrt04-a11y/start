# 運用 Runbook（障害対応プレイブック）

この Runbook は、日次/週次/月次の運用コマンド、代表的な障害と復旧手順、主要な環境変数、初動チェックリストをまとめたものです。

## 1) 定期運用コマンド

### 日次パイプライン

```powershell
powershell -ExecutionPolicy Bypass -File scripts/daily_pipeline.ps1
```

### 週次パイプライン

```powershell
powershell -ExecutionPolicy Bypass -File scripts/weekly_pipeline.ps1
```

### 月次パイプライン（推奨運用コマンド）

```powershell
python -m src.main monthly-report
python -m src.main apply-insights
python -m src.main retention
```

## 2) よくある失敗と対処（プレイブック）

### A. Connector failure（fetch failed / retry exhausted）

- 診断コマンド:
  ```powershell
  python -m src.main fetch github microsoft/vscode open 5
  python -m src.main doctor --json
  Select-String -Path logs\* -Pattern "retry exhausted|connector|command_failed" -CaseSensitive:$false
  ```
- 復旧コマンド例:
  ```powershell
  $env:CONNECTOR_RETRIES="5"
  $env:CONNECTOR_BACKOFF_SEC="1.0"
  python -m src.main fetch rss https://hnrss.org/frontpage 20
  ```
- 停止/ロールバック基準: 同一コネクタが連続2回失敗、または 15 分以内に改善しない場合はバッチ全体を停止し、直前の安定設定（既定値）へ戻す。
- エスカレーション条件: 「複数ソースで同時失敗」または「認証更新でも解消しない」場合は Platform/運用責任者へ即時連絡。

### B. Rate-limit wait exceeded（max wait exceeded）

- 診断コマンド:
  ```powershell
  Select-String -Path logs\* -Pattern "429|Retry-After|X-RateLimit-Reset|max wait" -CaseSensitive:$false
  python -m src.main fetch github microsoft/vscode open 20
  ```
- 復旧コマンド例:
  ```powershell
  $env:CONNECTOR_MAX_WAIT_SEC="60"
  python -m src.main weekly-report --days 3
  ```
- 停止/ロールバック基準: 待機上限引き上げ後も 2 サイクル連続で超過する場合は対象ジョブを停止し、`CONNECTOR_MAX_WAIT_SEC` を元値へ戻して対象期間を縮小する。
- エスカレーション条件: 日次/週次の SLA を超過見込み（30分以上遅延）になった時点で運用チャンネルへエスカレーション。

### C. Webhook failure（alert delivery failed）

- 診断コマンド:
  ```powershell
  Select-String -Path logs\alerts.log -Pattern "webhook_failed|ALERT_WEBHOOK" -CaseSensitive:$false
  python -m src.main doctor --json
  ```
- 復旧コマンド例:
  ```powershell
  $env:ALERT_WEBHOOK_FORMAT="slack"
  $env:ALERT_WEBHOOK_RETRIES="5"
  python -m src.main weekly-report --days 7
  ```
- 停止/ロールバック基準: 通知先に誤配信の可能性がある設定変更を行った場合は webhook 送信を一時停止し、`logs/alerts.log` 監視へ切り替える。
- エスカレーション条件: 重要アラートの通知欠落が 10 分以上継続したら SRE/通知基盤担当へ連絡。

### D. Doctor CI failure（doctor --json errors）

- 診断コマンド:
  ```powershell
  python -m src.main env-init
  python -m src.main doctor --json
  ```
- 復旧コマンド例:
  ```powershell
  python -m src.main doctor
  python -m src.main doctor --json
  ```
- 停止/ロールバック基準: `doctor --json` に `errors` が残る状態ではデプロイ/マージを停止する。
- エスカレーション条件: Secret 更新後も CI が連続2回失敗する場合は CI 管理者と機能オーナーへ同時エスカレーション。

### E. Issue sync duplication（重複起票）

- 診断コマンド:
  ```powershell
  Select-String -Path docs\improvement_backlog.md -Pattern "\[Promoted\]" -CaseSensitive:$false
  python -m src.main apply-insights --dry-run
  ```
- 復旧コマンド例:
  ```powershell
  $env:AUTO_SYNC_PROMOTED_ISSUES="0"
  python -m src.main apply-insights
  ```
- 停止/ロールバック基準: 同一 `period_key` で重複起票を確認した時点で自動同期を停止し、手動確認に切り替える。
- エスカレーション条件: 1 週で 3 件以上の重複起票、または既存 Issue 破壊的更新を検知した場合はプロダクトオーナーへ連絡。

### F. Retention problems（退避失敗/過剰退避）

- 診断コマンド:
  ```powershell
  python -m src.main retention
  Get-ChildItem archive | Select-Object -First 20
  Select-String -Path logs\* -Pattern "retention|archive|command_failed" -CaseSensitive:$false
  ```
- 復旧コマンド例:
  ```powershell
  $env:RETENTION_DAYS="120"
  python -m src.main retention
  ```
- 停止/ロールバック基準: 予期しない大量退避やディスク逼迫を検知したら retention を停止し、`RETENTION_DAYS` を直前値へ戻して再評価する。
- エスカレーション条件: 復元が必要なデータ欠落の疑い、またはディスク使用率 85% 超過でインフラ担当へ即時連絡。

## 3) Decision Matrix（症状 → アクション）

| 症状 | 初動アクション | Owner / Escalation |
| --- | --- | --- |
| connector が retry exhausted | 単体 fetch 再実行、`CONNECTOR_RETRIES/BACKOFF` 一時調整 | 当番運用、15分超で Platform |
| 429 で max wait exceeded | 重複ジョブ停止、対象期間縮小、`CONNECTOR_MAX_WAIT_SEC` 見直し | 当番運用、SLA遅延見込みで運用責任者 |
| webhook_failed が継続 | URL/format 検証、再試行値調整、ログ監視へ切替 | SRE、10分超で通知基盤担当 |
| CI doctor が errors | `env-init` + `doctor --json` をローカル再現、Secrets 修正 | PR担当、2回連続失敗でCI管理者 |
| Issue が同期間で重複起票 | `AUTO_SYNC_PROMOTED_ISSUES=0` で同期停止、手動整理 | 機能オーナー、週3件超でPO |
| retention 後に欠落/逼迫懸念 | retention 停止、`RETENTION_DAYS` 差し戻し、archive確認 | 運用 + インフラ、緊急時は即時エスカレーション |

## 4) 環境変数マトリクス（主要ノブ）

| 変数 | 用途 | 既定/例 |
| --- | --- | --- |
| `OPENAI_API_KEY` | AI 要約/API 利用 | 必須（AI機能利用時） |
| `RETENTION_DAYS` | 保持日数 | `90` |
| `CONNECTOR_RETRIES` | コネクタ再試行回数 | `3` |
| `CONNECTOR_BACKOFF_SEC` | コネクタ初期待機秒 | `0.5` |
| `CONNECTOR_MAX_WAIT_SEC` | レート制限待機上限秒 | `30` |
| `ALERTS_MAX_LINES` | alerts ローテーション閾値 | `500` |
| `ALERT_WEBHOOK_URL` | アラート通知先 | 任意 |
| `ALERT_WEBHOOK_FORMAT` | Webhook形式 | `generic` |
| `ALERT_WEBHOOK_RETRIES` | Webhook再試行回数 | `3` |
| `ALERT_WEBHOOK_BACKOFF_SEC` | Webhook初期待機秒 | `1.0` |
| `PROMOTED_MIN_COUNT` | Promoted 警告閾値 | `1` |
| `AUTO_SYNC_PROMOTED_ISSUES` | Issue自動同期有効化 | `0` / `1` |
| `GITHUB_REPO` | Issue同期先 | `owner/repo` |
| `GITHUB_TOKEN` | Issue同期トークン | 必須（同期時） |

## 5) インシデント初動チェックリスト（最初の15分）

1. 影響範囲を特定（失敗パイプライン: 日次/週次/月次、失敗時刻、直近変更）。
2. `logs/alerts.log` と CI ログを確認し、失敗種別を分類（connector / rate-limit / webhook / doctor / issue-sync / retention）。
3. 再現コマンドを単体実行し、恒常障害か一時障害かを切り分け。
4. 認証・環境変数（特に `OPENAI_API_KEY`、`GITHUB_TOKEN`、Webhook URL）を検証。
5. 緩和策を適用（再試行設定・待機上限・ジョブ分散など）し、再実行。
6. 5分以内に復旧しない場合、運用チャンネルへ状況共有（影響、暫定対処、次アクション、次回報告時刻）。

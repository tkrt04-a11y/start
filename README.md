# AI 駆動開発スターターキット

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Python による AI 駆動開発のための最小限・再利用可能なスターターキット**

このリポジトリは、AI プロジェクトをすぐに始めたい開発者向けに、基本的なプロジェクト構成、テンプレート化機構、CI/CD パイプラインを提供します。

## 含まれているもの

- 基本的なプロジェクト構成
- AI モデル（OpenAI SDK）を読み込み・利用するサンプルコード
- シンプルな CLI エントリポイント
- ユニットテスト
- 開発ガイドライン

## セットアップ

1. Python の仮想環境を作成・有効化：
   ```sh
   python -m venv venv
   .\venv\Scripts\activate
   ```
2. 依存関係をインストール：
   ```sh
   pip install -r requirements.txt
   ```

### OpenAI APIキーの取得と設定

1. OpenAI Platform にサインインし、APIキー発行画面を開く
   - `https://platform.openai.com/`
   - 画面上の `API keys` から新しいキーを作成
2. 取得したキーを Windows 環境変数へ設定
   ```powershell
   # 現在のターミナルだけ有効
   $env:OPENAI_API_KEY = "sk-..."

   # 恒久設定（新しいターミナルで有効）
   setx OPENAI_API_KEY "sk-..."
   ```
3. 設定確認
   ```powershell
   echo $env:OPENAI_API_KEY
   ```

#### より安全な設定方法（推奨）

キーをコマンドに直書きせず、対話入力で保存できます。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/set_openai_key.ps1
```

管理者権限でマシン全体に保存したい場合:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/set_openai_key.ps1 -Machine
```

この方法なら、キー文字列がターミナルのコマンド行に残りにくくなります。

## 使い方

メインスクリプトを実行：
```sh
python -m src.main
```

### 情報収集機能

AI 駆動開発に有益な情報を手動で記録するための簡単なコマンドを
用意しています。スターターキットの改善アイデアや調査結果を
集めるためのネタ帳として使えます。

```sh
# コマンドライン引数を渡す場合
python -m src.main collect "survey" "users want simpler API"

# 引数を省略すると対話で訊ねられます
python -m src.main collect
```

データは実行ディレクトリの `collected_data.json` に
JSON 形式で蓄積されます。

各エントリには `collected_at`（ISO 8601 の取得時刻）も保存され、
将来の時系列分析に利用できます。

収集した内容を簡単に確認するための分析コマンドも用意しています。
```sh
python -m src.main analyze
```
出力はソースごとのエントリ数です。

AI 要約付き分析:
```sh
python -m src.main analyze --ai --model gpt-4o-mini
```

`OPENAI_API_KEY` 未設定時や API クォータ超過（429）時は、
自動的にローカル要約（fallback）へ切り替わります。

### 自動収集コネクタ

GitHub Issues / RSS / Survey(JSON) から情報を自動で取り込めます。

```sh
# GitHub issues
python -m src.main fetch github microsoft/vscode open 20

# RSS
python -m src.main fetch rss https://hnrss.org/frontpage 20

# Survey JSON
python -m src.main fetch survey-json survey.json content
```

### 分析結果の反映

分析結果をスターターキット運用に反映するため、改善バックログと
指示ファイルの自動更新コマンドを提供しています。

```sh
python -m src.main apply-insights
python -m src.main apply-insights --ai
python -m src.main apply-insights --dry-run
```

`--dry-run` ではファイル書き込みを行わず、`docs/improvement_backlog.md` と `.github/instructions/common.instructions.md` の差分サマリー（new_file/unchanged/changed と行数増減）を表示します。

データ保持ポリシー（既定 90 日）を適用し、古いデータを `archive/` へ退避:

```sh
python -m src.main retention
```

この保持処理は `collected_data.json` / `logs/activity_history.jsonl` / `logs/alerts.log` に加えて、
`logs/*-metrics-*.json` も対象にし、期限超過ファイルを `archive/metrics/` へ退避します。

設定診断:
```sh
python -m src.main doctor
python -m src.main doctor --json
python -m src.main env-init
```

`doctor --json` は CI でも実行され、設定不整合（errors）をPR時に検知します。

`docs/weekly_reports/latest_weekly_report.md` が存在する場合、
Spotlight の `Action:` 項目を抽出して `docs/improvement_backlog.md` の
`## Spotlight Actions` チェックリストへ自動転記します。
このとき、変化量（Delta）の大きさに応じて `[High]` / `[Med]` / `[Low]` の
優先度ラベルを自動付与します。
また、バックログ出力時には `High → Med → Low` の順で自動整列されます。

週次レポート生成時（`weekly-report --days N`）には、Spotlight の `High` アクションが
`## Action Items` に `[Promoted]` 付きで自動昇格されます。

さらに `apply-insights` 実行時には、週次レポートの `[Promoted]` 項目が
`docs/improvement_backlog.md` の `## Promoted This Week` セクション先頭に同期されます。

`apply-insights` の実行ログには、同期された `Spotlight` / `Promoted` 件数も表示されるため、
日次・週次パイプラインのログ監視に利用できます。
`Promoted` 件数がしきい値未満（`PROMOTED_MIN_COUNT`、既定1）の場合は
`Warning: promoted actions below threshold (...)` が出力されます。
日次/週次パイプラインではこのしきい値判定を行い、`logs/alerts.log` に追記します。
`ALERTS_MAX_LINES`（既定500）を超えると `alerts-YYYYMMDD-HHMMSS.log` にローテーションされます。
`ALERT_WEBHOOK_URL` を設定すると、同アラートをWebhook通知します。
同一シグネチャ（タイムスタンプを除いたアラート本文）のWebhook通知は、`ALERT_DEDUP_COOLDOWN_SEC`（既定600秒）以内では抑止されます。
重複判定状態は `logs/alert_dedup_state.json` に保存され、クールダウン経過後は再送されます。
重複判定状態は `ALERT_DEDUP_TTL_SEC`（既定604800秒=7日）より古いエントリを自動削除し、状態ファイルの肥大化を防ぎます。
Webhookペイロード形式は `ALERT_WEBHOOK_FORMAT` で `generic` / `slack` / `teams` を選択できます（既定 `generic`）。
パイプラインの実行ログ（`logs/*-run-*.log` / `logs/alerts.log`）とアラートサマリ（`logs/alerts-summary-*.md`）は UTF-8（BOMなし）で出力されます。

重複抑止状態の確認/初期化:

```sh
python -m src.main alert-dedup-status
python -m src.main alert-dedup-status --json
python -m src.main alert-dedup-reset
python -m src.main alert-dedup-reset --backup
python -m src.main alert-dedup-prune
python -m src.main alert-dedup-prune --json
```

`alert-dedup-status` は `logs/alert_dedup_state.json` のエントリ数・最古/最新時刻・上位シグネチャを表示します。
`alert-dedup-reset` は状態を安全に空へ初期化し、`--backup` 指定時はバックアップファイルを作成します。
`alert-dedup-prune` はTTLに基づいて期限切れエントリを即時削除し、削除件数を表示します。

### Pipeline metrics artifacts

日次/週次/月次パイプライン実行後、`logs/` に機械可読なメトリクス JSON が出力されます（UTF-8, BOMなし）。

- `logs/daily-metrics-YYYYMMDD-HHMMSS.json`
- `logs/weekly-metrics-YYYYMMDD-HHMMSS.json`
- `logs/monthly-metrics-YYYYMMDD-HHMMSS.json`

各ファイルには、`pipeline`、`started_at`、`finished_at`、`duration_sec`、`command_failures`、`alert_count`、`promoted_threshold`、`promoted_detected`、`monthly_report_target`、`webhook_format`、`success` を含みます。

集約サマリー（直近30日、テキスト出力）:

```sh
python -m src.main metrics-summary
```

期間指定とJSON出力:

```sh
python -m src.main metrics-summary --days 7
python -m src.main metrics-summary --days 90 --json
```

しきい値チェック（違反ありで終了コード1）:

```sh
python -m src.main metrics-check
python -m src.main metrics-check --days 30
python -m src.main metrics-check --days 14 --json
```

CI（GitHub Actions）の `build` ジョブでは、テスト後に次の品質ゲートを実行します。

```sh
python -m src.main metrics-check --days 30 --json
```

`metrics-check --json` の出力仕様は `docs/schemas/metrics_check.schema.json` で固定化されています。
この JSON には `schema_version`（現行 `1.1.0`）が含まれます。
ローカル検証例:

```sh
python scripts/ci/validate_json_schema.py --input metrics-check-result.json --schema docs/schemas/metrics_check.schema.json --compatibility major
```

JSON Schema のバージョニング/互換性/破壊的変更/CI 運用方針は
`docs/schema_compatibility_policy.md` を参照してください。

しきい値違反が1件以上ある場合は終了コード `1` になり、ジョブは失敗します。
`pull_request` イベント時は、`metrics-check` 結果を PR コメントへ自動反映します。
コメントは `<!-- ai-starter:metrics-check -->` マーカー付きの単一コメントを更新する方式で、
毎回の実行で重複コメントを増やしません（違反なしの場合は `✅ pass` に更新）。
比較用の前回結果（`logs/metrics-check-ci-prev.json`）が存在する場合、
`violation_count` / `health_score`（存在時）/ pipeline別違反件数（daily/weekly/monthly）の差分も同コメントに表示します。
前回結果が無い、または読めない場合は比較セクションをスキップして継続します。
PR コメントには active な `threshold_profile` に加え、profile + 環境変数上書きを反映した
実効しきい値（`daily/weekly/monthly` の `max_duration_sec` / `max_failure_rate`）も表示されます。
同コメント末尾には `logs/ops-report-ci.json` の `failed_command_retry_guides` から、
`pipeline` / `suggested_retry_command` / `runbook_reference` を併記します（未取得時は案内文へ自動フォールバック）。
このコメント更新のため、CI ワークフローは最小権限として `contents: read` と `issues: write` を使用します。
運用ポリシーに合わせて、以下のしきい値環境変数をリポジトリ変数/環境変数として設定してください。

- `METRIC_THRESHOLD_PROFILE`（`dev` / `stg` / `prod`、既定 `prod`）
- `METRIC_MAX_DURATION_DAILY_SEC`
- `METRIC_MAX_DURATION_WEEKLY_SEC`
- `METRIC_MAX_DURATION_MONTHLY_SEC`
- `METRIC_MAX_FAILURE_RATE_DAILY`
- `METRIC_MAX_FAILURE_RATE_WEEKLY`
- `METRIC_MAX_FAILURE_RATE_MONTHLY`

`METRIC_THRESHOLD_PROFILE` はパイプライン別の既定しきい値セットを選択します。
`dev` は緩め、`stg` は中間、`prod` は厳しめの設定です。
不明な値が指定された場合は安全側として `prod` が適用されます。
個別の `METRIC_MAX_DURATION_*` / `METRIC_MAX_FAILURE_RATE_*` が設定されている場合、
それらが profile 既定値より優先されます。

`metrics-check` は直近期間の `logs/*-metrics-*.json` を評価し、
パイプライン別の実行時間上限（`max_duration_sec`）と失敗率上限（`failure_rate`）の違反を出力します。
違反が1件以上ある場合は終了コード `1`、違反なしは `0` です。

`metrics-summary` は `logs/*-metrics-*.json`（daily/weekly/monthly）を読み取り、
パイプライン別の実行回数・成功率・`duration_sec` の平均/最大・最新実行（timestamp/success）と、
全体の `command_failures` / `alert_count` 合計を出力します。
加えて、`health_score` と `health_breakdown`（`factors` / `penalties` / `formula`）を
text/json の両方で出力します。

ダッシュボード Metrics タブでは、同じ集計データから `Health score`（0-100）を表示します。
これは運用状態を 1 つの値で把握するための簡易指標で、次を組み合わせて算出します。

- パイプライン平均成功率（ペナルティ: `(1 - avg_success_rate) * 60`）
- しきい値違反件数（ペナルティ: `min(25, violations * 5)`）
- コマンド失敗件数（ペナルティ: `min(10, command_failures * 2)`）
- アラート件数（軽微な補助ペナルティ: `min(5, alert_count * 0.2)`）

最終スコアは `100 - (上記ペナルティ合計)` を `0..100` に丸め込みます。

また、`logs/weekly-ops-failure-diagnostic.md` がある場合は、
ダッシュボード Metrics タブに最新の failure diagnostic 要約
（生成時刻・失敗理由・必須ファイル検証の要点）を表示します。
ファイルが無い場合は案内メッセージのみ表示されます。

### 運用ヘルスレポート（週次）

運用状態をまとめたレポートを生成できます（既定は直近7日）。

```sh
python -m src.main ops-report
python -m src.main ops-report --days 14
python -m src.main ops-report --days 7 --json
python -m src.main ops-report-index --limit 8
```

生成ファイル:
- `docs/ops_reports/ops-report-YYYY-MM-DD.md`
- `docs/ops_reports/latest_ops_report.md`
- `docs/ops_reports/ops-report-YYYY-MM-DD.html`
- `docs/ops_reports/latest_ops_report.html`
- `docs/ops_reports/index.html`

`ops-report` 実行時には `docs/ops_reports/index.html` も自動更新され、最新レポートと直近レポート（Markdown/HTML）へのリンク一覧を出力します。
週次パイプライン（`scripts/weekly_pipeline.ps1`）では `ops-report` の直後に `ops-report-index` を実行し、index 更新漏れを防ぎます。

レポートには、パイプライン別成功率、`metrics-check` 相当のしきい値違反件数、`logs/alerts.log` の主要アラート種別、直近のコマンド失敗件数に加えて、
`logs/*-run-*.log` から抽出した失敗コマンド再実行ガイド（`pipeline` / `failed_command` / `suggested_retry_command` / `runbook_reference` / `runbook_reference_anchor`）も含みます。
`metrics-summary` と同一命名の `health_score` / `health_breakdown` を含みます（md/html/json）。
さらに、`logs/alerts-summary-YYYYMMDD.md`（日次）を自動収集し、ops-report に「Daily Alert Summaries」として添付します（`-weekly` 要約は除外）。
加えて、`logs/weekly-artifact-verify.json` の検証結果を `artifact_integrity`（json）/ `Artifact Integrity`（md/html）として取り込み、`OK/MISSING` と missing 件数を表示します。

`--json` を付けると、同じレポートファイル（Markdown/HTML）を生成しつつ、標準出力には機械可読な JSON ペイロードを出力します。

GitHub Actions の CI では `python -m src.main ops-report --days 7 --json > logs/ops-report-ci.json` を実行し、`ops-report-ci` artifact として `logs/ops-report-ci.json`（加えて `docs/ops_reports/latest_ops_report.md/html`）を保存します。

`ops-report --json` の出力仕様は `docs/schemas/ops_report.schema.json` で固定化されています。
この JSON には `schema_version`（現行 `1.1.0`）が含まれます。
ローカル検証例:

```sh
python scripts/ci/validate_json_schema.py --input logs/ops-report-ci.json --schema docs/schemas/ops_report.schema.json --compatibility major
```

週次公開向けに `.github/workflows/weekly-ops-report.yml` を追加しています。
この workflow はスケジュール実行または手動実行で `ops-report` と `ops-report-index` を実行し、`weekly-ops-report` artifact を生成します。
artifact upload 前に `python scripts/ci/verify_weekly_ops_artifacts.py --json-output logs/weekly-artifact-verify.json` で `docs/ops_reports/latest_ops_report.md` / `latest_ops_report.html` / `index.html` / `logs/ops-report-ci.json` の存在を検証し、欠落時はジョブを失敗させます。
ジョブ失敗時は `python scripts/ci/generate_weekly_failure_diagnostic.py` で診断レポートを生成し、`weekly-ops-failure-diagnostic` artifact（実行コマンド一覧、失敗判定理由、必須ファイル検証結果、最新ログ抜粋を含む）としてアップロードします。
既定では artifact 生成のみ（安全既定）で、`.github/pages-deploy.enabled` ファイルが存在する場合のみ GitHub Pages デプロイジョブが有効になります。

`AUTO_SYNC_PROMOTED_ISSUES=1`（または `--sync-issues`）を使うと、
`GITHUB_REPO` と `GITHUB_TOKEN` を使って Promoted actions を GitHub Issue に自動起票します。
同期間の重複起票を避けるため、Issue本文メタデータに `period_key` を記録し、
タイトル一致または `action_hash + period_key` 一致で重複判定します。
`period_key` は週次 Promoted では週ラベル（例: `2026-W09`）、月次 Promoted では月ラベル（例: `2026-02`）を使います。
Issue本文は `Source Period` / `Action` / `Context` / `Metadata` セクションの共通テンプレートで生成されます。
`GITHUB_ISSUE_PERIOD_LABELS=1` を有効化すると、週次は `ai-starter-weekly`、月次は `ai-starter-monthly` を既存ラベルに追加します。
Assignee は優先順位 `GITHUB_ISSUE_ASSIGNEES`（明示指定） > `GITHUB_ISSUE_ASSIGNEE_RULES`（ラベル一致） > `default` ルールで解決されます。
`GITHUB_ISSUE_ASSIGNEE_RULES` は `label:assignee1,assignee2;default:teamlead` 形式で指定し、
例: `ai-starter-weekly:alice;ai-starter-monthly:bob;default:teamlead`。
`GITHUB_ISSUE_ASSIGNEE_RULES` に不正な構文（例: `:` なし、空ラベル、空assignee）が含まれる場合、
安全のため Issue sync はスキップされ、エラーメッセージが出力されます。
Issue sync の GitHub API 呼び出しは 429 / secondary rate limit を検知すると待機して再試行します。
待機秒は `Retry-After` / `X-RateLimit-Reset` を優先し、未提供時は指数バックオフを使用し、失敗時は status/message/attempt を含むエラーを出力します。
`ISSUE_SYNC_RETRIES`（既定3）で再試行回数、`ISSUE_SYNC_BACKOFF_SEC`（既定1.0）で初期待機秒を上書きできます。
不正値が指定された場合は安全な既定値にフォールバックし、警告ログで判別できます。
月次側は `docs/monthly_reports/latest_monthly_report.md` の `## Promotable Actions` から `[Promoted]` を抽出して同期します。

主要な `.env` 設定値:
- `OPENAI_API_KEY`: OpenAI API キー
- `RETENTION_DAYS`: データ保持日数（既定90）
- `PROMOTED_MIN_COUNT`: Promoted 最低件数しきい値（既定1）
- `ALERTS_MAX_LINES`: `logs/alerts.log` ローテーション行数（既定500）
- `ALERT_WEBHOOK_URL`: アラートWebhook URL（任意）
- `ALERT_WEBHOOK_FORMAT`: Webhookペイロード形式（`generic` / `slack` / `teams`、既定`generic`）
- `ALERT_WEBHOOK_RETRIES`: Webhook通知のリトライ回数（既定3）
- `ALERT_WEBHOOK_BACKOFF_SEC`: Webhook通知の初期待機秒（指数バックオフ、既定1.0）
- `ALERT_DEDUP_COOLDOWN_SEC`: 同一アラートのWebhook重複抑止クールダウン秒（既定600、0で無効化）
- `ALERT_DEDUP_TTL_SEC`: 重複抑止状態エントリの保持秒（既定604800=7日、0でTTL pruning無効化）
- `CONNECTOR_RETRIES`: 収集コネクタのリトライ回数（既定3）
- `CONNECTOR_BACKOFF_SEC`: リトライ初期待機秒（既定0.5）
- `CONNECTOR_MAX_WAIT_SEC`: レート制限待機の最大秒数（既定30）
- `METRIC_THRESHOLD_PROFILE`: しきい値プロファイル（`dev` / `stg` / `prod`、既定`prod`、不明値は`prod`へフォールバック）
- `METRIC_MAX_DURATION_DAILY_SEC`: 日次 `max_duration_sec` 上限秒（既定900）
- `METRIC_MAX_DURATION_WEEKLY_SEC`: 週次 `max_duration_sec` 上限秒（既定1800）
- `METRIC_MAX_DURATION_MONTHLY_SEC`: 月次 `max_duration_sec` 上限秒（既定3600）
- `METRIC_MAX_FAILURE_RATE_DAILY`: 日次 `failure_rate` 上限（0-1、既定0.10）
- `METRIC_MAX_FAILURE_RATE_WEEKLY`: 週次 `failure_rate` 上限（0-1、既定0.20）
- `METRIC_MAX_FAILURE_RATE_MONTHLY`: 月次 `failure_rate` 上限（0-1、既定0.25）
- `METRIC_SLO_CONSECUTIVE_ALERT_N`: 連続失敗の warning 判定閾値（既定3）
- `METRIC_SLO_CONSECUTIVE_ALERT_CRITICAL_N`: 連続失敗の critical 判定閾値（既定5、warning閾値以上へ補正）
- `AUTO_SYNC_PROMOTED_ISSUES`: `1` でIssue自動起票を有効化
- `GITHUB_REPO`: `owner/repo` 形式
- `GITHUB_TOKEN`: GitHub API トークン
- `GITHUB_ISSUE_LABELS`: Issueに付与するラベル（`,`区切り）
- `GITHUB_ISSUE_ASSIGNEES`: Issueに割り当てるユーザー（`,`区切り）
- `GITHUB_ISSUE_ASSIGNEE_RULES`: ラベルベースのassigneeルーティング（`;`区切り、`label:assignee1,assignee2` 形式、`default` でフォールバック。不正構文はsyncスキップ）
- `GITHUB_ISSUE_PERIOD_LABELS`: `1` で週次/月次の期間ラベル自動付与（既定0）
- `ISSUE_SYNC_RETRIES`: Issue sync の再試行回数（既定3）
- `ISSUE_SYNC_BACKOFF_SEC`: Issue sync の初期待機秒（指数バックオフ基準、既定1.0）

### 週次レポート

週ごとのサマリーを Markdown として出力できます。

```sh
python -m src.main weekly-report
python -m src.main weekly-report --ai
python -m src.main weekly-report --days 14
python -m src.main weekly-report --all
```

デフォルトは直近 7 日です（`--days N` で変更、`--all` で全期間）。
直近 N 日を使う場合は、同じ長さの前期間との比較（増減）もレポートに表示されます。

生成ファイル:
- `docs/weekly_reports/weekly-report-YYYY-Www.md`
- `docs/weekly_reports/latest_weekly_report.md`
- `docs/weekly_reports/weekly-report-YYYY-Www.html`
- `docs/weekly_reports/latest_weekly_report.html`

### 月次レポート

月ごとのサマリーを Markdown/HTML として出力できます。

```sh
python -m src.main monthly-report
python -m src.main monthly-report --month 2026-02
python -m src.main monthly-report --ai
```

`--month` を省略した場合は当月（`YYYY-MM`）が対象です。
月次レポートは `collected_at` を持つデータのみ対象とし、時刻欠損エントリは含めません。
比較可能なデータがある場合、前月比（PoP）の増減と Spotlight（Top 3 Changes / 推奨アクション）を表示します。

生成ファイル:
- `docs/monthly_reports/monthly-report-YYYY-MM.md`
- `docs/monthly_reports/latest_monthly_report.md`
- `docs/monthly_reports/monthly-report-YYYY-MM.html`
- `docs/monthly_reports/latest_monthly_report.html`

`scripts/daily_pipeline.ps1` と `scripts/weekly_pipeline.ps1` では、月初（毎月1日）に前月分（`YYYY-MM`）の `monthly-report --ai` を自動実行します。
`scripts/monthly_pipeline.ps1` は毎回、前月分（`YYYY-MM`）の `monthly-report --ai` を自動実行します。

生成/更新される主なファイル:
- `docs/improvement_backlog.md`
- `.github/instructions/common.instructions.md`（Auto Insights ブロック）
- `docs/issue_roadmap.md`（優先度順Issueと実施順タスク管理台帳）

重複データは `source + content`（空白・大文字小文字を正規化）で自動除外されるため、
日次実行でも同一エントリが無限に増えにくい設計です。

### Web UI

Streamlit ダッシュボードで収集・分析・自動取得・反映を操作できます。

```sh
streamlit run src/dashboard.py
```

`History` タブでは、操作履歴を時刻付きで確認できます（`logs/activity_history.jsonl`）。
`Alerts` タブでは、`logs/alerts.log` の件数と最新アラートを確認できます。
同タブで `daily/weekly/unknown` のパイプライン内訳と `threshold/webhook_failed/command_failed/other` の種別内訳（指定期間）も確認できます。
※ チャットUIそのものの時刻表示はこのリポジトリからは制御できないため、代替として操作履歴を提供しています。
`Metrics` タブでは、パイプラインの実行回数、成功率、実行時間（平均/最大）、合計（`command_failures`/`alert_count`）、およびパイプラインごとの最新実行情報を表示します。
同タブに `Issue Sync 監視` カードを追加し、成功件数/失敗件数/再試行件数を表示します（`logs/activity_history.jsonl` / `logs/activity_log.jsonl` を優先、未取得項目は `N/A`、次点で `logs/*-run-*.log` から集計）。
同タブ内で `docs/ops_reports/latest_ops_report.md` の最新サマリ（カード表示）と、`docs/ops_reports/ops-report-*.md` の履歴プレビューも参照できます。
同タブの `Ops Report（最新）` では `Daily Alert Summaries` を表形式で表示し、ops-report 側に未記載の場合は `logs/alerts-summary-YYYYMMDD.md`（日次）からフォールバック表示します。

HTTP収集コネクタはリトライ対応です（`CONNECTOR_RETRIES`、`CONNECTOR_BACKOFF_SEC`）。
429 または GitHub レート制限ヘッダー時は、`X-RateLimit-Reset` / `Retry-After` を見て `CONNECTOR_MAX_WAIT_SEC`（既定30秒）以内で待機して再試行します。
また、ETag / If-Modified-Since を使う条件付きフェッチ最適化により、重複トラフィックを抑制します。

### 運用 Runbook（障害対応）

障害時の初動、代表的な失敗パターン、環境変数の主要ノブは `docs/runbook.md` を参照してください。

### 定期実行登録（Windows Task Scheduler）

日次/週次/月次のタスクは、統合スクリプトで一括または選択登録する運用を推奨します。

全パイプラインを既定値で登録（daily/weekly/monthly）:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_pipeline_tasks.ps1
```

週次と月次のみ登録:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_pipeline_tasks.ps1 -Pipelines weekly,monthly
```

時刻・曜日・日付をまとめて変更:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_pipeline_tasks.ps1 -DailyTime "21:30" -WeeklyDay MON -WeeklyTime "08:30" -MonthlyDay 5 -MonthlyTime "08:45"
```

実行せずに登録コマンドだけ確認（DryRun）:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_pipeline_tasks.ps1 -Pipelines weekly,monthly -DryRun
```

実行前の入力検証のみ実施（ValidateOnly）:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_pipeline_tasks.ps1 -Pipelines daily,weekly -DailyTime "21:30" -WeeklyDay MON -WeeklyTime "08:30" -ValidateOnly
```

既定値:
- Daily: `AIStarterDailyPipeline` / `09:00`
- Weekly: `AIStarterWeeklyPipeline` / `SUN` / `09:30`
- Monthly: `AIStarterMonthlyPipeline` / `1日` / `10:00`

後方互換のため、従来スクリプトも引き続き利用できます。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_daily_task.ps1 -Time "21:30" -DryRun
powershell -ExecutionPolicy Bypass -File scripts/register_weekly_task.ps1 -Day MON -Time "08:30" -ValidateOnly
powershell -ExecutionPolicy Bypass -File scripts/register_monthly_task.ps1 -Day 5 -Time "08:45"
```


## テスト

```sh
pytest
```

## 注意事項

- 必要な AI ライブラリ（例: openai、transformers）を `requirements.txt` に追加してください。
- 環境変数（API キーなど）を適切に設定してください。

## Cookiecutter テンプレート

`cookiecutter-ai-starter/` にカスタマイズ可能なテンプレートが含まれています。これを使えば、自分のプロジェクト名や設定でスターターキットの新しいコピーをすばやく作成できます。

### 1. インストール

```sh
pip install cookiecutter        # まだインストールしていない場合
```

### 2. テンプレートから生成

```sh
cookiecutter d:\GitHub\start\cookiecutter-ai-starter
```

実行すると対話形式で以下のように質問されます（括弧内はデフォルト値）：

```
project_name [AI Starter Project]: My Awesome App
project_slug [ai_starter]: awesome_app
description [A minimal AI-driven development project]: An app that uses AI
python_version [3.11]: 3.11
```

入力が完了すると、現在のディレクトリに `awesome_app` というフォルダが作成され、その中にスターターキットのファイルがコピーされます。プロジェクト名やスラッグは `cookiecutter.json` 内で定義されている変数です。

### 3. 生成後の手順

```sh
cd awesome_app
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

以降は通常のセットアップ・実行・テスト手順に従います。

### 4. テンプレートのカスタマイズ

- `cookiecutter.json` に要素を追加すると、新たな質問が発生します。
- テンプレート内のファイル名や内容で `{{cookiecutter.<name>}}` を利用すれば動的に置換されます。
- たとえば、`{{cookiecutter.project_slug}}/src/{{cookiecutter.project_slug}}.py` のように書けます。

これにより、プロジェクト固有の情報をテンプレート化できます。

---

（このセクションはドキュメントに自動的に反映され、サイトにも詳細な説明が出力されます。）

## Copilot / ChatGPT 向け指示

このスターターキットは GitHub Copilot や ChatGPT のチャット機能で
“リポジトリの前提”を与えるためのサンプル指示ファイルを含みます。

指示は `.github/instructions/common.instructions.md` に置いてあります。

ファイル内では
```yaml
---
description: リポジトリ全体の共通ガイドラインを Copilot Chat に提供します。
applyTo: "**/*"
---
```
のようにメタデータを記載でき、実際の指示を Markdown 形式で続けます。

詳細は Qiita 記事『Github Copilotを標準機能の範囲で賢くしよう』を参考に
必要に応じてファイルを追加・編集してください。

## ウェブサイト

ドキュメントサイトは `docs/index.html` にあり、リポジトリの Pages を有効にしてソースに `docs/` を指定すると GitHub Pages で公開できます。このページにはセットアップ、実行、テスト、テンプレートの使い方が説明されています。

サイトは `main` ブランチへのプッシュごとに README や他の Markdown ソースから自動再生成されるため、スターターキットの最新状態を常に反映します。

## ライセンス

このプロジェクトは MIT ライセンス下で公開されています。詳細は [LICENSE](LICENSE) ファイルを参照してください。

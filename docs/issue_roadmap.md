# Issue Roadmap（優先度順実施計画）

更新日: 2026-03-01

このドキュメントは、今後の改善提案を Issue として管理し、優先度の高い順に順次実施するための台帳です。

## 運用ルール

- 優先度は `P0 > P1 > P2`。
- 実施は原則として上から順（依存がある場合は依存先を優先）。
- 1つ完了したら次を `in-progress` に切り替える。
- 変更は root と cookiecutter template の両方へ同期する。
- 各 Issue の完了条件を満たし、`python -m pytest -q` が通ることを完了基準とする。

## P0（最優先）

### ISSUE-001: データ保持ポリシー（自動アーカイブ/削除）
- Priority: P0
- Status: done
- 背景: `collected_data.json` と `logs` が継続運用で肥大化する。
- 実装方針:
  - 保持日数（例: `RETENTION_DAYS`）を `.env` で管理。
  - 期限超過データを `archive/` へ退避、必要に応じて削除。
  - 日次/週次パイプライン実行時に保持処理を自動実行。
- 完了条件:
  - 保持処理のCLIまたは関数が追加される。
  - 期限超過データが実際にアーカイブされるテストがある。

### ISSUE-002: `doctor --json` のCI厳格化（warning閾値）
- Priority: P0
- Status: done
- 背景: 現状は errors のみで失敗。運用上は warning も一部失敗条件にしたい。
- 実装方針:
  - `DOCTOR_FAIL_ON_WARNINGS=1` で warning もCI失敗に切り替え可能。
  - workflow で環境変数切替をサポート。
- 完了条件:
  - workflow と doctor の挙動が環境変数で切替可能。
  - テストで warning fail の分岐確認。

### ISSUE-003: `apply-insights --dry-run` の差分表示
- Priority: P0
- Status: done
- 背景: dry-runで「何が変わるか」が見えづらい。
- 実装方針:
  - 更新対象ファイルごとの差分サマリ（追加/変更行数、主なセクション）を表示。
- 完了条件:
  - dry-run実行時に変更見込み情報が表示される。
  - 既存ファイルは実際に書き換わらない。

## P1（高）

### ISSUE-004: Webhook通知の再送制御（retry/backoff）
- Priority: P1
- Status: done
- 背景: Webhook送信失敗時に単発失敗で通知が失われる。
- 実装方針:
  - `ALERT_WEBHOOK_RETRIES`, `ALERT_WEBHOOK_BACKOFF_SEC` を追加。
  - パイプライン内の送信を指数バックオフで再試行。
- 完了条件:
  - 再試行ロジックが入り、ログに試行回数が残る。

### ISSUE-005: Issue起票の冪等性強化（タイトル+期間キー）
- Priority: P1
- Status: done
- 背景: 類似タスクが期間違いで重複起票される可能性。
- 実装方針:
  - タイトルだけでなく、期間キー（週ラベル）で重複判定。
  - 既存Issue本文にメタ情報を埋め込み判定を安定化。
- 完了条件:
  - 重複起票が抑止されるテストがある。

### ISSUE-006: アラート通知テンプレートの選択式化（Slack/Teams）
- Priority: P1
- Status: done
- 背景: 通知先により期待payload形式が異なる。
- 実装方針:
  - `ALERT_WEBHOOK_FORMAT=generic|slack|teams` を追加。
  - 送信payloadを形式別に整形。
- 完了条件:
  - formatごとのpayload生成が確認できる。

### ISSUE-007: Dashboard のアラート詳細分析（種別/パイプライン別）
- Priority: P1
- Status: done
- 背景: 件数推移は見えるが原因軸の分析が弱い。
- 実装方針:
  - 種別（threshold/webhook-failed/etc）とdaily/weekly別の集計表示。
- 完了条件:
  - Alertsタブで種別・パイプライン別集計が表示される。

## P2（中）

### ISSUE-008: 収集コネクタの条件付き取得（ETag/If-Modified-Since）
- Priority: P2
- Status: done
- 背景: 同一データ取得による無駄なトラフィックを減らしたい。
- 実装方針:
  - 取得時メタ（etag/last-modified）を保存して再利用。
- 完了条件:
  - 304応答でスキップできる。

### ISSUE-009: レート制限ヘッダ連動の待機
- Priority: P2
- Status: done
- 背景: 固定backoffよりもAPIヘッダ連動のほうが安定。
- 実装方針:
  - GitHubの rate limit/reset ヘッダに応じて待機時間を調整。
- 完了条件:
  - ヘッダありケースで待機ロジックが反映される。

### ISSUE-010: 月次レポート出力
- Priority: P2
- Status: done
- 背景: 週次に加えて中期トレンド可視化が必要。
- 実装方針:
  - `monthly-report` コマンド追加。
  - docs 配下に md/html を生成。
- 完了条件:
  - 月次レポートが生成される。

### ISSUE-011: Runbook整備（障害時対応手順）
- Priority: P2
- Status: done
- 背景: 運用引き継ぎの属人化を防ぐ。
- 実装方針:
  - 代表障害（API失敗、Webhook失敗、Issue sync失敗）の対処手順を文書化。
- 完了条件:
  - `docs/runbook.md` が作成され、主要障害ケースを網羅。

### ISSUE-012: 月次パイプラインと月次タスク登録
- Priority: P1
- Status: done
- 背景: 日次/週次に比べ、月次運用の実行導線が手動寄り。
- 実装方針:
  - `scripts/monthly_pipeline.ps1` を追加。
  - `scripts/register_monthly_task.ps1` で Task Scheduler 登録を標準化。
- 完了条件:
  - 月次パイプラインと登録スクリプトが root/template 両方に存在。

### ISSUE-013: Alerts表示名の可読化
- Priority: P2
- Status: done
- 背景: Dashboard の alerts 種別キーが内部名で表示され、運用者が把握しづらい。
- 実装方針:
  - 表示層のみ日本語ラベルへ変換。
- 完了条件:
  - 内部キー互換を維持しつつ、表示が可読ラベル化される。

### ISSUE-014: パイプラインログの UTF-8 統一
- Priority: P1
- Status: done
- 背景: PowerShell の既定出力経路により UTF-16 混在が発生し、ログ閲覧性が低下。
- 実装方針:
  - ログ/サマリ書き込みを UTF-8 で明示出力するヘルパーへ統一。
- 完了条件:
  - 日次/週次/月次パイプラインのログ出力が UTF-8 で統一される。

### ISSUE-015: 月次レポートの前月比較（PoP）
- Priority: P2
- Status: done
- 背景: 月次は単月サマリのみで、増減トレンドの把握が弱い。
- 実装方針:
  - 前月との source 別 delta と Spotlight を追加。
- 完了条件:
  - 月次レポートに前月比較セクションが表示される。

### ISSUE-016: パイプライン実行メトリクス JSON 出力
- Priority: P1
- Status: done
- 背景: 監視連携には機械可読な実行メトリクスが必要。
- 実装方針:
  - daily/weekly/monthly ごとに metrics JSON を `logs/` 配下へ出力。
- 完了条件:
  - 実行時間、成否、失敗件数、アラート件数などが JSON で保存される。

### ISSUE-017: Runbook 障害プレイブック拡張
- Priority: P2
- Status: done
- 背景: 初動手順は整備済みだが、復旧判断基準と具体コマンド例を強化したい。
- 実装方針:
  - 障害種別ごとに復旧コマンド例・切り戻し判断を追加。
- 完了条件:
  - `docs/runbook.md` に障害別プレイブックが拡張される。

### ISSUE-018: メトリクス集約サマリ
- Priority: P1
- Status: done
- 背景: 個別 metrics JSON はあるが、横断的な運用把握に集約出力が必要。
- 実装方針:
  - `metrics-summary` コマンドで期間集約（件数/成功率/duration/最新実行）を提供。
- 完了条件:
  - CLI で human/json の両形式で集約結果を取得できる。

### ISSUE-019: Dashboard メトリクス可視化
- Priority: P1
- Status: done
- 背景: 集約結果を GUI で即時把握できる運用導線が必要。
- 実装方針:
  - Dashboard に Metrics タブを追加し、成功率・duration・失敗件数を表示。
- 完了条件:
  - ダッシュボード上で metrics 集約を可視化できる。

### ISSUE-020: メトリクス閾値アラート
- Priority: P1
- Status: done
- 背景: 指標の悪化を早期検知するため、しきい値監視が必要。
- 実装方針:
  - `metrics-check` コマンドを追加し、duration/failure-rate の閾値違反を検知。
- 完了条件:
  - 閾値違反時に非0終了コードと違反内容出力が得られる。

### ISSUE-021: タスク登録一元化
- Priority: P2
- Status: done
- 背景: 日次/週次/月次の登録スクリプトが分散し、運用設定の再現性が低い。
- 実装方針:
  - `register_pipeline_tasks.ps1` を追加して一括登録を標準化。
- 完了条件:
  - 単一コマンドで daily/weekly/monthly の登録を選択実行できる。

### ISSUE-022: CI への metrics-check 統合
- Priority: P1
- Status: done
- 背景: 閾値違反をCI段階で検知しないと、劣化が本番運用まで持ち越される。
- 実装方針:
  - GitHub Actions で `metrics-check --days 30 --json` を品質ゲートとして実行。
- 完了条件:
  - 閾値違反時に CI ジョブが失敗する。

### ISSUE-023: Dashboard 直近違反一覧
- Priority: P1
- Status: done
- 背景: 指標悪化の原因把握に、違反詳細の一覧表示が必要。
- 実装方針:
  - Metrics タブに Recent Violations セクションを追加。
- 完了条件:
  - pipeline/metric/observed/threshold などの違反情報をGUIで確認できる。

### ISSUE-024: metrics 保持ポリシー
- Priority: P1
- Status: done
- 背景: metrics JSON が長期運用で蓄積し、ログ管理コストが増大する。
- 実装方針:
  - retention 対象に `logs/*-metrics-*.json` を追加し `archive/metrics` へ退避。
- 完了条件:
  - retention 実行結果に metrics moved/kept が含まれる。

### ISSUE-025: 月次 Promoted の Issue 同期
- Priority: P2
- Status: done
- 背景: 週次のみ自動起票だと、月次の重要アクションが取りこぼされる。
- 実装方針:
  - 月次レポートの High アクションを抽出し Issue 同期対象へ追加。
  - `period_key=YYYY-MM` で冪等判定。
- 完了条件:
  - 月次 Promoted が重複抑止つきで同期される。

### ISSUE-026: 通知重複抑止（cooldown）
- Priority: P1
- Status: done
- 背景: 同一違反通知が短時間で連続送信され、運用ノイズが増える。
- 実装方針:
  - `ALERT_DEDUP_COOLDOWN_SEC` と `logs/alert_dedup_state.json` による重複抑止。
- 完了条件:
  - cooldown 内の同一通知は抑止され、期限後に再通知される。

### ISSUE-027: 運用ヘルスレポート自動生成
- Priority: P1
- Status: done
- 背景: 運用健全性を定点観測するレポートが不足。
- 実装方針:
  - `ops-report` コマンドを追加し、週次で運用ヘルスを集計出力。
- 完了条件:
  - `docs/ops_reports/` に md/html が生成され、週次パイプラインへ統合される。

### ISSUE-028: ops-report の Dashboard 閲覧
- Priority: P2
- Status: done
- 背景: 運用レポートがファイルのみだと参照導線が弱い。
- 実装方針:
  - Dashboard の Metrics タブで最新/履歴 ops-report を閲覧可能にする。
- 完了条件:
  - 最新表示と履歴プレビューが Dashboard から利用できる。

### ISSUE-029: メトリクス閾値の環境プロファイル化
- Priority: P1
- Status: done
- 背景: 開発/検証/本番で許容閾値が異なる。
- 実装方針:
  - `METRIC_THRESHOLD_PROFILE=dev|stg|prod` を導入。
  - 明示 env は profile 値を上書き。
- 完了条件:
  - profile 切替と env 優先上書きが動作する。

### ISSUE-030: CI で ops-report 成果物保存
- Priority: P1
- Status: done
- 背景: CI 実行時の運用ヘルススナップショットを追跡したい。
- 実装方針:
  - `ops-report --json` をCIで実行し、artifactとして保存。
- 完了条件:
  - CI artifact に ops-report JSON（必要に応じ md/html 併載）が含まれる。

### ISSUE-031: dedup 状態の可視化とリセット
- Priority: P2
- Status: done
- 背景: 通知抑止が効いているか運用者が確認しづらい。
- 実装方針:
  - `alert-dedup-status` / `alert-dedup-reset` コマンドを追加。
- 完了条件:
  - dedup state の確認と手動リセットが可能。

### ISSUE-032: 自動起票テンプレート統一
- Priority: P2
- Status: done
- 背景: 週次/月次で起票本文・ラベル規約が分散。
- 実装方針:
  - issue 本文テンプレートを共通化。
  - `GITHUB_ISSUE_PERIOD_LABELS=1` で period ラベル付与を選択可能化。
- 完了条件:
  - 週次/月次で一貫した本文構造とラベル挙動になる。

### ISSUE-033: ops-report の週次公開導線
- Priority: P1
- Status: done
- 背景: 週次運用レポートを継続的に公開・参照できる導線が必要。
- 実装方針:
  - `docs/ops_reports/index.html` を自動更新し、Actions で公開向け成果物を生成。
- 完了条件:
  - latest/履歴レポートへのリンク index が維持される。

### ISSUE-034: metrics-check の PR コメント投稿
- Priority: P1
- Status: done
- 背景: CI 結果をPR上で即時把握したい。
- 実装方針:
  - metrics-check 結果を PR コメントへ upsert（重複抑止）する。
- 完了条件:
  - PR ごとに最新の metrics 判定コメントが1件で維持される。

### ISSUE-035: dedup state TTL 掃除
- Priority: P1
- Status: done
- 背景: alert dedup state の長期肥大化を防ぐ必要がある。
- 実装方針:
  - `ALERT_DEDUP_TTL_SEC` を導入し、期限切れ state を自動 prune。
- 完了条件:
  - dedup state が TTL ベースで自動的にクリーンアップされる。

### ISSUE-036: 起票 assignee ルーティング
- Priority: P2
- Status: done
- 背景: 期間・ラベルに応じた担当振り分けを自動化したい。
- 実装方針:
  - `GITHUB_ISSUE_ASSIGNEE_RULES` によるラベル/期間ベース割当を追加。
- 完了条件:
  - 明示 assignee 優先を維持しつつ、ルールベース自動割当が機能する。

### ISSUE-037: Dashboard 運用ヘルススコア
- Priority: P2
- Status: done
- 背景: 複数運用指標を単一スコアで素早く把握したい。
- 実装方針:
  - success/violation/failure/alert を組み合わせた 0-100 スコアを表示。
- 完了条件:
  - Metrics タブでヘルススコアと主要内訳を確認できる。

### ISSUE-038: ヘルススコア表示の命名統一
- Priority: P2
- Status: done
- 背景: CLI / Dashboard / レポート間でスコア項目名の揺れがあり、運用認知コストが高い。
- 実装方針:
  - `health_score` / `health_breakdown` の命名を共通化し、表示揺れを解消。
- 完了条件:
  - 主要導線で同一フィールド名に統一される。

### ISSUE-039: metrics PRコメントへのプロファイル明示
- Priority: P1
- Status: done
- 背景: PR 上で閾値結果を読む際に、どのプロファイルで評価されたか分かりづらい。
- 実装方針:
  - metrics-check コメントに `METRIC_THRESHOLD_PROFILE` と実効閾値情報を追記。
- 完了条件:
  - PR コメントだけで評価条件が判別できる。

### ISSUE-040: タスク登録 DryRun/ValidateOnly
- Priority: P1
- Status: done
- 背景: Task Scheduler への登録前に安全確認したい。
- 実装方針:
  - `register_pipeline_tasks.ps1` に `-DryRun` / `-ValidateOnly` を追加し、wrapper からも透過指定可能にする。
- 完了条件:
  - 実登録せずに検証のみ実行できる。

### ISSUE-041: assignee ルール構文チェック
- Priority: P1
- Status: done
- 背景: `GITHUB_ISSUE_ASSIGNEE_RULES` の誤記が静かに無視されると、担当割当の不整合に気づきづらい。
- 実装方針:
  - ルールパーサを厳密化し、不正構文を検出して Issue sync を安全にスキップする。
- 完了条件:
  - 不正構文時に明確なメッセージが出力され、sync 実行が抑止される。

### ISSUE-042: alerts 日次要約の ops-report 添付
- Priority: P2
- Status: done
- 背景: 日次アラートの傾向を週次運用レポートから追跡しづらい。
- 実装方針:
  - `logs/alerts-summary-YYYYMMDD.md` を収集し、ops-report に日次要約セクションとして添付する。
- 完了条件:
  - ops-report（json/md/html）で直近の日次アラート要約を参照できる。

### ISSUE-043: Ops Report / metrics-check JSONスキーマ固定化
- Priority: P1
- Status: done
- 背景: JSON 出力仕様の暗黙変更を CI で検知しづらい。
- 実装方針:
  - `ops-report --json` と `metrics-check --json` の JSON Schema を追加し、CI で検証する。
- 完了条件:
  - スキーマ適合チェックが CI に組み込まれ、破壊的変更を検知できる。

### ISSUE-044: 日次アラート要約の Dashboard 表示
- Priority: P2
- Status: done
- 背景: 日次アラート要約を運用UIから参照しづらい。
- 実装方針:
  - Metrics/Ops Report 導線で Daily Alert Summaries を表示し、必要時はログ要約ファイルをフォールバック利用する。
- 完了条件:
  - Dashboard 上で日次要約の件数・失敗傾向を確認できる。

### ISSUE-045: 失敗コマンド再実行ガイド自動生成
- Priority: P1
- Status: done
- 背景: 障害時の初動で再実行コマンドの特定に時間がかかる。
- 実装方針:
  - run log から失敗コマンドを抽出し、ops-report に再実行候補と runbook 参照を添付する。
- 完了条件:
  - ops-report（json/md/html）で再実行ガイドを参照できる。

### ISSUE-046: Issue Sync のレート制限耐性強化
- Priority: P1
- Status: done
- 背景: 429/secondary rate limit で Issue 同期が不安定になる。
- 実装方針:
  - `Retry-After` / `X-RateLimit-Reset` を優先した待機と再試行を追加する。
- 完了条件:
  - 再試行成功・枯渇失敗の双方がテストで検証される。

### ISSUE-047: 週次公開 artifact 完全性チェック
- Priority: P1
- Status: done
- 背景: 週次公開成果物の欠落を後段で気づくリスクがある。
- 実装方針:
  - weekly workflow に必須ファイル検証を追加し、欠落時はジョブ失敗とする。
- 完了条件:
  - 必須ファイル欠落時に CI が fail-fast する。

### ISSUE-048: runbook参照リンクの自動アンカー化
- Priority: P2
- Status: done
- 背景: 再実行ガイドの runbook 参照先を即時に開ける導線が必要。
- 実装方針:
  - runbook 参照文字列からアンカーを生成し、ops-report の Markdown/HTML でリンク化する。
- 完了条件:
  - 再実行ガイドから runbook の該当節へ直接遷移できる。

### ISSUE-049: metrics-check 結果の履歴比較コメント
- Priority: P1
- Status: done
- 背景: PR 上で結果の前回差分が見えず、劣化判断がしづらい。
- 実装方針:
  - PR コメント生成時に previous/current を比較し、違反件数やスコア差分を表示する。
- 完了条件:
  - previous がある場合、PR コメントに差分が表示される（無い場合は安全にスキップ）。

### ISSUE-050: Dashboard の Issue Sync 監視カード
- Priority: P2
- Status: done
- 背景: Issue sync の成功/失敗を UI で継続監視したい。
- 実装方針:
  - activity/run log を集約し、Dashboard に success/failure/retry の監視カードを追加する。
- 完了条件:
  - Dashboard で Issue sync の健全性を確認できる。

### ISSUE-051: weekly workflow 失敗時診断 artifact
- Priority: P1
- Status: done
- 背景: weekly workflow 失敗時の原因調査を迅速化したい。
- 実装方針:
  - 失敗時に診断Markdownを生成し、要点ログ・検証結果を artifact として保存する。
- 完了条件:
  - 失敗時に診断 artifact が自動保存される。

### ISSUE-052: スキーマ互換性ポリシー文書化
- Priority: P2
- Status: done
- 背景: JSON schema 更新時の互換性判断基準を明文化したい。
- 実装方針:
  - versioning / breaking change / CI運用ルールを docs に整理する。
- 完了条件:
  - root/template ともに同等ポリシー文書と README 導線が存在する。

### ISSUE-053: Issue Sync retry設定の環境変数化
- Priority: P1
- Status: done
- 背景: API混雑時の再試行挙動を環境別に調整したい。
- 実装方針:
  - `ISSUE_SYNC_RETRIES` / `ISSUE_SYNC_BACKOFF_SEC` を導入し、不正値は安全既定へフォールバックする。
- 完了条件:
  - env 指定と不正値フォールバックの双方がテストで検証される。

### ISSUE-054: Dashboard で weekly診断要約表示
- Priority: P2
- Status: done
- 背景: 失敗時診断 artifact を画面上で即確認したい。
- 実装方針:
  - `logs/weekly-ops-failure-diagnostic.md` から要点抽出し、Metrics 導線に表示する。
- 完了条件:
  - 生成時刻・失敗理由・必須ファイル検証の要点を Dashboard で確認できる。

### ISSUE-055: schema version導入と互換チェック自動化
- Priority: P1
- Status: done
- 背景: JSONスキーマの互換性崩れを早期検知したい。
- 実装方針:
  - payload に `schema_version` を導入し、CI で major 互換チェックを自動実行する。
- 完了条件:
  - schema検証と major mismatch 検知がテスト/CIで機能する。

### ISSUE-056: PRコメントにrunbookリンクと再実行ガイド併記
- Priority: P1
- Status: done
- 背景: PR上で障害時アクションを即判断できる情報が不足。
- 実装方針:
  - metrics PRコメントに ops-report 由来の再実行ガイドと runbook 参照を追記する。
- 完了条件:
  - ガイド情報がある場合は表形式で表示、無い場合は安全にスキップされる。

### ISSUE-057: artifact完全性結果のops-report取込
- Priority: P1
- Status: done
- 背景: weekly artifact 検証結果を運用レポートへ集約したい。
- 実装方針:
  - 完全性検証スクリプトのJSON出力を workflow で保存し、ops-report と Dashboard へ取り込む。
- 完了条件:
  - `artifact_integrity` 情報を ops-report(json/md/html) と Dashboard で確認できる。

### ISSUE-058: CIにシークレット自動検査を追加
- Priority: P0
- Status: done
- 背景: push/PR時のシークレット混入をCI段階で早期検知したい。
- 実装方針:
  - 追跡ファイルを対象にシークレットパターン検査スクリプトを追加し、CIで実行する。
  - プレースホルダ値はallowlistで誤検知を回避する。
- 完了条件:
  - CIでsecret scanが実行され、検知時はジョブ失敗となる。

### ISSUE-059: Workflow権限の最小化
- Priority: P0
- Status: done
- 背景:不要な権限付与は事故時の影響範囲を広げる。
- 実装方針:
  - workflow全体は `contents: read` を基本とし、必要なjobのみ job-level でwrite権限を付与する。
- 完了条件:
  - python-app / weekly-ops-report の権限が最小化される。

### ISSUE-060: Release作成の半自動化
- Priority: P1
- Status: done
- 背景: 手動リリース作成の入力ミス・手順ブレを減らしたい。
- 実装方針:
  - `workflow_dispatch` でタグ/タイトル/notes file を受け取る release workflow を追加する。
- 完了条件:
  - 手動トリガーでReleaseを作成できるworkflowが root/template に存在する。

### ISSUE-061: 失敗診断artifactへ再現コマンドセット付与
- Priority: P1
- Status: done
- 背景: 失敗時の初動を短縮するため、再現手順をartifact内に明示したい。
- 実装方針:
  - weekly failure diagnostic に `Reproduction Commands` セクションを追加する。
- 完了条件:
  - 診断artifactとDashboardで再現コマンドを確認できる。

### ISSUE-062: Dashboardに運用SLOビュー追加
- Priority: P2
- Status: done
- 背景: 成功率の目標達成状況を運用UIで即時把握したい。
- 実装方針:
  - パイプライン別の目標成功率(SLO)と実績を比較し、PASS/FAILを表示する。
- 完了条件:
  - Metrics タブにSLO表と未達警告が表示される。

## 実施順（初期設定）

1. ISSUE-001
2. ISSUE-002
3. ISSUE-003
4. ISSUE-004
5. ISSUE-005
6. ISSUE-006
7. ISSUE-007
8. ISSUE-008
9. ISSUE-009
10. ISSUE-010
11. ISSUE-011
12. ISSUE-012
13. ISSUE-013
14. ISSUE-014
15. ISSUE-015
16. ISSUE-016
17. ISSUE-017
18. ISSUE-018
19. ISSUE-019
20. ISSUE-020
21. ISSUE-021
22. ISSUE-022
23. ISSUE-023
24. ISSUE-024
25. ISSUE-025
26. ISSUE-026
27. ISSUE-027
28. ISSUE-028
29. ISSUE-029
30. ISSUE-030
31. ISSUE-031
32. ISSUE-032
33. ISSUE-033
34. ISSUE-034
35. ISSUE-035
36. ISSUE-036
37. ISSUE-037
38. ISSUE-038
39. ISSUE-039
40. ISSUE-040
41. ISSUE-041
42. ISSUE-042
43. ISSUE-043
44. ISSUE-044
45. ISSUE-045
46. ISSUE-046
47. ISSUE-047
48. ISSUE-048
49. ISSUE-049
50. ISSUE-050
51. ISSUE-051
52. ISSUE-052
53. ISSUE-053
54. ISSUE-054
55. ISSUE-055
56. ISSUE-056
57. ISSUE-057
58. ISSUE-058
59. ISSUE-059
60. ISSUE-060
61. ISSUE-061
62. ISSUE-062

---

## 進捗ログ

- 2026-02-28: Issue台帳を初版作成。
- 2026-02-28: ISSUE-001, 002, 003, 004, 005, 007 を順次実装完了（root/template同期・回帰通過）。
- 2026-02-28: ISSUE-006 を実装完了（Webhook payload format: generic/slack/teams）。
- 2026-02-28: ISSUE-008, 009 を実装完了（条件付き取得・レート制限ヘッダ連動待機）。
- 2026-02-28: ISSUE-010, 011 を実装完了（月次レポート出力・Runbook整備）。
- 2026-03-01: ISSUE-012, 013, 014, 016 を実装完了（月次パイプライン自動化・Alerts表示改善・ログUTF-8統一・メトリクスJSON出力）。
- 2026-03-01: ISSUE-015, 017, 018, 019, 020, 021 を実装完了（月次PoP比較・Runbook拡張・メトリクス集約/可視化/閾値監視・タスク登録一元化）。
- 2026-03-01: ISSUE-022, 023, 024, 025, 026, 027 を実装完了（CI品質ゲート・違反可視化・metrics保持・月次Promoted同期・通知重複抑止・運用ヘルスレポート）。
- 2026-03-01: ISSUE-028, 029, 030, 031, 032 を実装完了（ops-report閲覧・閾値プロファイル化・CI成果物保存・dedup状態管理・起票テンプレ統一）。
- 2026-03-01: ISSUE-033, 034, 035, 036, 037 を実装完了（週次公開導線・PRコメント連携・dedup TTL掃除・assigneeルーティング・運用ヘルススコア）。
- 2026-03-01: ISSUE-038, 039, 040, 041, 042 を実装完了（命名統一・PRプロファイル明示・タスク登録DryRun/ValidateOnly・ルール構文チェック・日次アラート要約添付）。
- 2026-03-01: ISSUE-043, 044, 045, 046, 047 を実装完了（JSONスキーマ固定化・Dashboard日次要約表示・再実行ガイド自動化・Issue Sync再試行強化・artifact完全性チェック）。
- 2026-03-01: ISSUE-048, 049, 050, 051, 052 を実装完了（runbookアンカー化・PR差分コメント・Issue Sync監視カード・失敗診断artifact・スキーマ互換性ポリシー文書化）。
- 2026-03-01: ISSUE-053, 054, 055, 056, 057 を実装完了（retry環境変数化・診断要約Dashboard表示・schema version互換検証・PR再実行ガイド併記・artifact完全性結果のops取込）。
- 2026-03-01: ISSUE-058, 059, 060, 061, 062 を実装完了（CI secret scan追加・workflow権限最小化・Release workflow追加・診断artifact再現コマンド追加・Dashboard SLO表示）。

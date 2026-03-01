# Changelog

## 2026-03-01

### Added
- 日次/週次/月次のパイプラインスクリプトとタスク登録スクリプトを追加。
- Webhook通知（フォーマット切替・再試行・指数バックオフ）と重複通知抑止を追加。
- メトリクス集計、Operational Health Score、Ops Report生成、Ops Report Index生成を追加。
- 週次アーティファクト整合性検証と失敗診断レポート生成を追加。
- Promoted actions の GitHub Issue 同期（期間キー重複防止、レート制限再試行）を追加。
- JSON Schema 検証CLIと `schema_version` 互換性（major）チェックを追加。
- ダッシュボードにアラート分析、Issue Sync監視、Ops Report/Failure Diagnostic表示を追加。

### Changed
- CIを拡張し、`metrics-check` / `ops-report` のスキーマ検証とPRコメント生成を強化。
- ドキュメント（運用手順・Runbook・スキーマ互換方針・ロードマップ）を更新。

### Security
- コミット対象を監査し、実シークレット混入がないことを確認。
- ローカル生成物の誤コミット防止のため `.gitignore` を強化（`logs/`, `collected_data.json`, `metrics-check-result.json`, `docs/*_reports/`, `docs/improvement_backlog.md`, `survey.json`）。

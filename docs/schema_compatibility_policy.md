# JSON Schema 互換性ポリシー

この文書は、`docs/schemas/` 配下の JSON Schema（現行: `metrics_check.schema.json`, `ops_report.schema.json`）を安全に運用するための互換性ポリシーを定義します。

## 1. スキーマ配置と管理単位

- 正式なスキーマ配置先は `docs/schemas/` とする。
- Cookiecutter テンプレート側は `cookiecutter-ai-starter/{{cookiecutter.project_slug}}/docs/schemas/` を同等の配置先とし、原則同内容を維持する。
- 1 ファイル = 1 契約（1 つの機械可読出力の仕様）として管理する。

## 2. バージョニング方針

- スキーマ変更は SemVer（`MAJOR.MINOR.PATCH`）の考え方で分類する。
  - `MAJOR`: 破壊的変更（後方互換なし）
  - `MINOR`: 後方互換を保つ機能追加（任意フィールド追加など）
  - `PATCH`: 仕様意図を変えない軽微修正（説明更新、誤記修正、過度でない制約緩和など）
- バージョンは PR 説明または変更ログ（本リポジトリでは本ドキュメント更新を含む）で明示する。
- 機械可読 JSON 出力には `schema_version` を必須で含め、各 schema の `properties.schema_version` を `const` または `enum` で定義する（現行 `1.1.0`）。

## 3. 互換性ルール

### Backward compatibility（後方互換）

既存コンシューマーが新スキーマ由来データを読み取れる状態を維持する。

推奨変更:
- 任意プロパティの追加
- 既存プロパティの説明拡充
- バリデーション制約の緩和（既存有効データを無効化しない範囲）

### Forward compatibility（前方互換）

新コンシューマーが旧データを読み取れる状態を維持する。

推奨実装:
- 新規必須項目は即時導入せず、段階的導入（まず任意項目として追加）
- 読み取り側は未知フィールドを無視可能にする

## 4. Breaking change 判定ルール

次を含む変更は原則 Breaking change とみなす。

- `required` への項目追加
- 既存項目の削除・改名
- 型変更（例: `string` → `number`）
- 列挙値の削除、制約強化（既存データを不正化する変更）
- 既存出力で許容されていた値の不許可化

Breaking change を行う場合:
- PR タイトルまたは説明で `BREAKING` を明示する
- 影響範囲（生成側/利用側/CI）と移行手順を同一 PR に記載する
- 必要に応じて移行猶予期間（旧新フォーマット併存期間）を設ける

## 5. 更新手順（どこをどう更新するか）

1. 対象スキーマを更新する（`docs/schemas/*.schema.json`）。
2. 同変更をテンプレート側スキーマ
   `cookiecutter-ai-starter/{{cookiecutter.project_slug}}/docs/schemas/*.schema.json`
   に反映する。
3. 本ドキュメントと `README.md` / テンプレート `README.md` の参照・説明を必要に応じ更新する。
4. 代表的な出力 JSON を使ってローカル検証する。

例:

```sh
python scripts/ci/validate_json_schema.py --input metrics-check-result.json --schema docs/schemas/metrics_check.schema.json --compatibility major
python scripts/ci/validate_json_schema.py --input logs/ops-report-ci.json --schema docs/schemas/ops_report.schema.json --compatibility major
```

## 6. CI 運用方針

- CI では JSON 出力が対応スキーマに適合することを継続的に確認する。
- CI ではスキーマ検証に加え `schema_version` の互換性チェック（少なくとも `major` 不一致を fail）を実行する。
- スキーマ更新 PR では、スキーマ本体だけでなく生成側/利用側コードを同一 PR で整合させる。
- 互換性に影響する変更では、PR で互換性区分（`MAJOR/MINOR/PATCH`）を明示する。
- 互換性リスクが高い変更（Breaking change）にはレビュー時に移行手順の記載を必須とする。

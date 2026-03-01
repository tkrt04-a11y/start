---
description: リポジトリ全体の共通ガイドラインを Copilot Chat に提供します。
applyTo: "**/*"
---

# AI Starter Kit 共通ルール

このリポジトリは AI 駆動開発プロジェクトの雛形です。
Copilot や ChatGPT のチャット指示を利用する場合、
以下のような前提を与えると有用です。

- プロジェクトは Python ベースであり、`src/` にコードがある。
- ユニットテストは `tests/` 以下にある。
- ドキュメントは `docs/` に HTML 形式で生成される。
- `cookiecutter-ai-starter` テンプレートを使って新規プロジェクトを作成する。

このファイルは `.github/instructions` 下に配置されており、
チャットの指示は GitHub 上で自動的に読み込まれます。

追加のフォルダ・拡張子単位で細かい指示が必要な場合は、
別ファイルを同ディレクトリに作成してください。

(元ネタ: Qiita『Github Copilotを標準機能の範囲で賢くしよう』)

<!-- auto-insights:start -->
## Auto Insights
収集データから頻出した情報源（上位）:
- github:microsoft/vscode
- rss:https://hnrss.org/frontpage
- manual
- survey
<!-- auto-insights:end -->

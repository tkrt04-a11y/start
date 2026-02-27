# AI 駆動開発スターターキット

このリポジトリは Python による AI 駆動開発のための最小限のスターターキットを提供します。含まれているもの：

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

## 使い方

メインスクリプトを実行：
```sh
python -m src.main
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

## ウェブサイト

ドキュメントサイトは `docs/index.html` にあり、リポジトリの Pages を有効にしてソースに `docs/` を指定すると GitHub Pages で公開できます。このページにはセットアップ、実行、テスト、テンプレートの使い方が説明されています。

サイトは `main` ブランチへのプッシュごとに README や他の Markdown ソースから自動再生成されるため、スターターキットの最新状態を常に反映します。

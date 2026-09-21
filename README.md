# nano-code (Python 版)

[`nano-code`](https://github.com/laiso/nano-code)（TypeScript / Bun 実装）を参考に Python で再実装した、最小構成のコーディングエージェントです。
書籍「作って学ぶ AIエージェント」で解説されているアーキテクチャ（思考ループ、ツール呼び出し、承認ゲート、
コンテキスト圧縮、サンドボックス実行、GitHub Actions 連携など）を Python (asyncio) で移植しています。

## 必要要件

- Python 3.11 以上
- LLM APIキー（OpenAI, Anthropic, Google のいずれか）

## セットアップ

DevContainer で開くと `postCreateCommand` が依存関係を自動インストールします（[`nano-code`](https://github.com/laiso/nano-code) の
`bun install` と同じ役割です）。コンテナは本プロジェクト専用なので、仮想環境（venv）は使わずコンテナの Python に直接インストールしています。

手動でインストールする場合は以下を実行してください（非rootユーザーで動かす前提のため `--user` を付けています）。

```bash
pip install --user -e ".[dev]"
# もしくは: pip install --user -r requirements.txt
```

環境変数ファイルを作成して編集します。

```bash
cp .env.example .env
```

`.env` に以下の値を設定します。

   - `LLM_PROVIDER`: 利用する LLM プロバイダー名を指定します（例: `openai`, `anthropic`, `google`）
   - `LLM_MODEL`: 利用するモデル名を指定します
   - `LLM_API_KEY`: 利用する LLM の API キーを指定します

## 使い方

```bash
python bin/cli.py "タスク内容"
```

主なオプション:

- `--yolo`: ツール実行の承認ゲートを自動承認する
- `--stream`: ストリーミング出力を使う
- `--sandbox`: `bwrap` を使ったプロセス隔離サンドボックスで `execCommand` を実行する（Linux + bubblewrap が必要）
- `--allowed-domains a.com,b.com`: `webFetch` ツールが許可するドメインを追加する

## PR レビューエージェント

GitHub Actions 上で、指定した PR の差分をレビューしてコメントを投稿するエージェントです。

```bash
PULL_REQUEST_NUMBER=123 python bin/review.py
```

## テスト

```bash
pytest -q
```

## ディレクトリ構成

```
.
├── bin/
│   ├── cli.py       # エージェント CLI エントリポイント
│   └── review.py    # PR レビューエージェント（GitHub Actions 用）
├── src/
│   ├── types.py            # 共通の型定義（Message, Tool, LanguageModel など）
│   ├── config.py            # グローバル設定（サンドボックス有効/無効、許可ドメイン）
│   ├── core/
│   │   ├── agent.py          # 思考ループ本体
│   │   ├── approval.py       # 対話的な承認プロンプト
│   │   ├── generate_text.py  # 非ストリーミング生成
│   │   ├── generate_stream.py# ストリーミング生成
│   │   ├── prompt.py / prompt.md  # システムプロンプト読み込み
│   │   ├── sandbox.py        # bwrap サンドボックス
│   │   └── security.py       # 機密ファイル・危険コマンド検出
│   ├── providers/
│   │   ├── model_factory.py      # 環境変数からプロバイダーを組み立てる
│   │   ├── anthropic_provider.py
│   │   ├── openai_provider.py
│   │   ├── google_provider.py
│   │   └── clean_messages.py     # 履歴圧縮後のツール呼び出し整合性補正
│   └── tools/
│       ├── read_file.py / write_file.py / edit_file.py
│       ├── exec_command.py / exec_command_sandbox.py
│       ├── git_tools.py / github_tools.py
│       └── web_fetch.py
├── tests/            # pytest（TypeScript 版の *.test.ts を移植）
└── workspace/         # エージェントの作業ディレクトリ（AGENTS.md を配置可能）
```

## TypeScript 版との違い

- ストリーミング API（付録A）は簡略化しつつ移植していますが、OpenAI Responses API（付録B）は移植対象外です。
- `execCommand` の許可コマンドは Bun/Node 前提から Python 前提（`python`, `pip`, `pytest` など）に置き換えています。
- Google プロバイダーは `google-genai` SDK の JSON Schema 互換フィールド（`parameters_json_schema`）を使用しており、
  ツールの `parameters`（標準 JSON Schema）をそのまま渡せます。
- それ以外のロジック（思考ループ、コンテキスト圧縮、承認ゲート、セキュリティチェック等）は TypeScript 版の実装に忠実に移植しています。

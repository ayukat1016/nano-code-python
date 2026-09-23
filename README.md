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

## GitHub Actions 連携

`.github/workflows/` に以下の2つのワークフローがあります（[`nano-code`](https://github.com/laiso/nano-code) の同名ワークフローを Python 向けに移植したものです）。

- `nano-code-review.yml`: PR が作成・更新されるたびに `bin/review.py --yolo` を実行し、差分をレビューしてコメントを投稿します。`secure-agent` という Environment を指定しており、人間の承認（Approve）を経てから実行されます。
- `nano-code.yml`: `workflow_dispatch`（手動実行、タスク内容を入力可能）または Issue 作成時に `bin/cli.py --yolo` を実行し、コード修正・コミット・PR作成・Issueへのコメントまで自動で行います。

利用するには、リポジトリに以下を設定してください。

- Secrets: `LLM_API_KEY`
- Variables: `LLM_PROVIDER`, `LLM_MODEL`
- Environment: `secure-agent`（`nano-code-review.yml` 用。レビュアーによる承認を必須にする場合は Settings > Environments で保護ルールを設定）

`GITHUB_TOKEN` は GitHub Actions が自動生成するものをそのまま使用します。

### 動作確認手順

事前に、リポジトリの Settings > Actions > General > Workflow permissions で
「Allow GitHub Actions to create and approve pull requests」を有効にしてください。
これが無効だと `createPullRequest` ツールの `gh pr create` が権限エラーで失敗します。

**`nano-code.yml`（Issue駆動エージェント）を試す**

Issue を作成すると自動でトリガーされます。

```bash
gh issue create \
  --repo <owner>/<repo> \
  --title "calculator.pyにテストを追加" \
  --body "calculator.py の関数にユニットテストを追加してください。"
```

正常に動作すると、エージェントが `workspace/calculator.py` と `workspace/test_calculator.py` を作成し、
ブランチ作成 → コミット → プッシュ → プルリクエスト作成 → 元のIssueへのコメント、まで自動で行います。

このとき作られるプルリクエストは `GITHUB_TOKEN` を使って `github-actions[bot]` が作成したものになるため、
`author_association` が `NONE` になります。後述の `nano-code-review.yml` は
「PR作成者が OWNER/MEMBER/COLLABORATOR の場合のみ動作する」という条件になっているため、
このPRに対しては**意図的にスキップ**されます（信頼できない入力からエージェントが自動でコード変更・自動レビュー・自動承認までを連鎖させてしまわないようにするためのセキュリティ上のガードです）。

**`nano-code-review.yml`（PRレビューエージェント）を試す**

`nano-code-review.yml` の動作を確認するには、自分のアカウントで直接プルリクエストを作成する必要があります。

```bash
git checkout -b <branch-name>
# 何かファイルを変更してコミット
git add <file>
git commit -m "..."
git push -u origin <branch-name>
gh pr create --repo <owner>/<repo> --title "..." --body "..."
```

PRを作成すると `nano-code-review.yml` がトリガーされますが、`secure-agent` Environment に
レビュアーを設定している場合はジョブが `waiting`（承認待ち）状態になります。
GitHub の Actions 画面から対象の実行を開き、Review deployments > Approve で承認すると
`bin/review.py --yolo` が実行され、レビューコメントがPRに投稿されます。

## テスト

```bash
pytest -q
```

## ディレクトリ構成

```
.
├── .github/
│   └── workflows/
│       ├── nano-code.yml         # Issue駆動 / 手動実行のコーディングエージェント
│       └── nano-code-review.yml  # PRレビューエージェント
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

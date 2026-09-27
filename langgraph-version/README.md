# nano-code (LangGraph版)

`nano-code-python`(スクラッチ実装)の思考ループ・承認ゲート・マルチプロバイダー対応を、
[LangGraph](https://langchain-ai.github.io/langgraph/) / [LangChain](https://python.langchain.com/) で
書き直すとどうなるかを確認するための比較用実装です。

このディレクトリは独立したPythonパッケージとして動きます(親の `src/` には依存しません)。

## スクラッチ実装との対応関係

| 役割 | スクラッチ実装(`src/`) | LangGraph版(このディレクトリ) |
|---|---|---|
| 思考ループ本体 | `core/agent.py`(while文で手書き、約210行) | `agent.py` の `StateGraph`(ノード2つ+条件分岐エッジ、約70行) |
| 承認ゲート | `core/approval.py` + `Agent`内の`needs_approval`チェック | `langgraph.types.interrupt()` / `Command(resume=...)` |
| コンテキスト管理 | `Agent._manage_context`(文字数ベースの手書き圧縮ロジック) | 未実装(LangGraphの`checkpointer`はあるが、本書と同じ圧縮戦略は自前実装が必要) |
| マルチプロバイダー対応 | `providers/{openai,anthropic,google}_provider.py`(各社SDKを個別にラップ、計750行超) | `langchain-openai`/`langchain-anthropic`/`langchain-google-genai`(統一された`BaseChatModel`インタフェースにモデル名を渡すだけ) |
| ツール定義 | `tools/{read_file,write_file,edit_file}.py`(`Tool`dataclass + 手書きJSON Schema) | `tools.py`(`@tool`デコレータが型ヒントからJSON Schemaを自動生成) |
| プロジェクト固有指示(AGENTS.md) | `core/prompt.py`(`workspace/AGENTS.md`があれば読み込み追記) | `cli.py`の`load_instructions()`(同じ挙動を移植) |
| ストリーミング/サンドボックス/Git連携/CI | 実装あり | **未実装**(スコープ外。後述) |

## コード量の比較

同等の機能(思考ループ・承認ゲート・マルチプロバイダー・基本3ツール)で比較すると:

```
スクラッチ実装（該当ファイル合計）: 1322 行
LangGraph版（このディレクトリ全体）:  302 行
```

約4分の1になっています。特に削減が大きいのはプロバイダー実装(`openai_provider.py`等、
各社SDKのレスポンス形式・ツール呼び出し形式の差異を1つずつ吸収するコードが1ファイルあたり
200〜250行)で、LangChainの統一インタフェースに任せることで丸ごと不要になります。

## 実装のポイント

### 思考ループ = グラフの2ノード + 条件分岐

```python
graph.add_node("agent", call_model)   # LLM呼び出し
graph.add_node("tools", run_tools)    # ツール実行
graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
graph.add_edge("tools", "agent")      # ループバック
```

`while current_step < max_steps: ...` という手書きループが、グラフのエッジ定義に置き換わります。
ループの最大回数は `graph.invoke(..., config={"recursion_limit": N})` で制御します。

### 承認ゲート = interrupt() / Command(resume=...)

`writeFile` / `editFile` / `execCommand` のように承認が必要なツールの実行前に
`interrupt({"tool": name, "args": args})` を呼ぶと、グラフの実行がそこで一時停止し、
呼び出し側(CLI)に制御が戻ります。人間が承認すると `Command(resume=True)` で、
拒否すると `Command(resume=False)` で再開します。停止中の状態を保持するために
`checkpointer=MemorySaver()` が必須です(本番用途では永続化可能なcheckpointerに差し替える)。

## 実装していないもの(スコープ外)

「LangGraphで書くとどう変わるか」を確認する目的の最小実装のため、以下は含めていません。

- コンテキスト圧縮(`manageContext`相当) — LangGraphにも会話トリミングの仕組みはあるが、
  本書と同じ「ツール結果を要約→古い順に削除」という戦略は別途実装が必要
- `--sandbox`(bubblewrapによるプロセス隔離)
- Git/GitHub連携ツール(`createBranch`/`commit`/`createPullRequest`等)
- ストリーミング出力
- GitHub Actions連携(`nano-code.yml`/`nano-code-review.yml`相当)

## セットアップ・実行方法

```bash
cd langgraph-version
pip install --user -r requirements.txt
```

親ディレクトリの `.env`(`LLM_PROVIDER`/`LLM_MODEL`/`LLM_API_KEY`または各社`_API_KEY`)をそのまま利用します。

```bash
python cli.py "workspace 内に hello.py を作成して 'Hello' を出力するようにしてください"
```

主なオプション:

- `--yolo`: 承認ゲートを自動承認する

### 動作確認手順

`workspace/AGENTS.md`(計算ユーティリティライブラリの規約: 純粋関数優先、
エラーは戻り値で表現、型ヒント必須)を実際に読ませつつ、ファイル作成→テスト実行までの
一連の流れを試すには以下を実行します。

```bash
cd langgraph-version
python cli.py "calculator.py に add, subtract, multiply, divide の4つの関数を実装し、test_calculator.py にpytestのテストを追加してください。" --yolo
```

正常に動作すると、エージェントがTODOリストを作成し、`writeFile`→`writeFile`→`execCommand`(pytest実行)の順に
自動承認されながら進み、最後に実装内容とテスト結果(例: `pytest: 9 passed`)を報告します。
`workspace/AGENTS.md` の規約が反映され、`divide`のゼロ除算等のエラーは例外ではなく
`(None, "Division by zero")` のような戻り値として実装されることを確認できます。

`--yolo` を外すと `writeFile`/`execCommand` のたびに y/n で承認を求められます(手動承認フローの確認用)。

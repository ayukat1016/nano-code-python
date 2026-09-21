#!/usr/bin/env python3
"""GitHub Actions 上で PR の差分をレビューするエージェント。

使用法:
    PULL_REQUEST_NUMBER=123 python bin/review.py [--yolo] [--sandbox]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from src.config import config  # noqa: E402
from src.core.agent import Agent, AgentConfig  # noqa: E402
from src.core.prompt import load_instructions  # noqa: E402
from src.providers.model_factory import create_model_from_env  # noqa: E402
from src.tools.exec_command import parse_command  # noqa: E402
from src.types import LanguageModel, Message, Tool  # noqa: E402

WORKSPACE_ROOT = REPO_ROOT / "workspace"
MAX_FILE_SIZE = 100 * 1024
ALLOWED_COMMANDS = ["python", "python3", "pip", "pytest", "ls", "pwd", "mkdir", "git", "gh"]
MAX_OUTPUT_LENGTH = 2000


def _mask_secret(value: Optional[str]) -> str:
    """機密情報をマスクする（ログ出力用）。"""
    if not value:
        return "(未設定)"
    if len(value) <= 8:
        return "***"
    return value[:4] + "***" + value[-4:]


def _write_temp_file(content: str, prefix: str) -> str:
    """PRレビュー用の一時ファイル書き込み（WORKSPACE_ROOT に保存）。"""
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    temp_path = WORKSPACE_ROOT / f".{prefix}-{int(time.time() * 1000)}.txt"
    temp_path.write_text(content, encoding="utf-8")
    return str(temp_path)


def _clean_review_path(path: str) -> str:
    """エージェントが workspace/ 相対のパスでアクセスしてきた場合に、
    実際のファイルがリポジトリルートに存在することを想定してパスをクリーンアップする。
    """
    if path.startswith("workspace/"):
        return path[len("workspace/"):]
    if path.startswith("./workspace/"):
        return path[len("./workspace/"):]
    if path.startswith("../"):
        return path[len("../"):]
    return path


async def _review_read_file_execute(args: dict[str, Any]) -> str:
    path = args["path"]
    clean_path = _clean_review_path(path)

    absolute_path = os.path.normpath(os.path.join(str(REPO_ROOT), clean_path))
    allowed_prefix = str(REPO_ROOT) + os.sep

    if not absolute_path.startswith(allowed_prefix) and absolute_path != str(REPO_ROOT):
        raise ValueError(f"アクセス拒否: {path} はリポジトリの外部です")

    def read_sync() -> str:
        try:
            real_path = os.path.realpath(absolute_path, strict=True)
        except FileNotFoundError as error:
            raise ValueError(f"ファイルが見つかりません: {path}") from error

        if not real_path.startswith(allowed_prefix) and real_path != str(REPO_ROOT):
            raise ValueError(f"アクセス拒否: {path} はシンボリックリンク経由でリポジトリ外を参照しています")

        if not os.path.isfile(real_path):
            raise ValueError(f"通常ファイルではありません: {path}")
        if os.path.getsize(real_path) > MAX_FILE_SIZE:
            raise ValueError(f"ファイルが大きすぎます: {path}")

        with open(real_path, "r", encoding="utf-8") as f:
            return f.read()

    return await asyncio.to_thread(read_sync)


review_read_file = Tool(
    name="readFile",
    description="リポジトリ内の指定されたファイルのパスから内容を読み込む。100KB以下のファイルのみ読み込めます。",
    needs_approval=False,
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": '読み込むファイルの相対パス（例: "src/tools/github.py"）'},
        },
        "required": ["path"],
    },
    execute=_review_read_file_execute,
)


async def _run_review_subprocess(command_name: str, command_args: list[str], cwd: str, timeout: float = 30) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            command_name,
            *command_args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as error:
        raise RuntimeError(f"コマンド実行エラー: {error}") from error

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"コマンドがタイムアウトしました ({timeout}秒)")

    stdout = stdout_bytes.decode(errors="replace")
    stderr = stderr_bytes.decode(errors="replace")

    if len(stdout) >= MAX_OUTPUT_LENGTH:
        stdout = stdout[:MAX_OUTPUT_LENGTH] + "\n... (出力が長いため省略されました)"
    if len(stderr) >= MAX_OUTPUT_LENGTH:
        stderr = stderr[:MAX_OUTPUT_LENGTH] + "\n... (出力が長いため省略されました)"

    if proc.returncode == 0:
        return stdout + (f"\n(stderr: {stderr.strip()})" if stderr else "")

    raise RuntimeError(f"コマンドが異常終了しました (exit code: {proc.returncode})\n{stderr}")


async def _review_exec_command_execute(args: dict[str, Any]) -> str:
    command = args["command"]
    # $ は正規表現や引数の文字列（ドル記号など）で頻出するため除外（shell=False で実行されるため安全）
    import re

    if re.search(r"[;&`]", command):
        raise ValueError("セキュリティ上の理由により、シェルメタ文字を含むコマンドは実行できません")

    parts = parse_command(command)
    command_name = parts[0] if parts else ""
    command_args = parts[1:]

    if command_name not in ALLOWED_COMMANDS:
        raise ValueError(f"コマンド {command_name} は許可されていません")

    # 引数のパス制限を REPO_ROOT 基準にする
    allowed_prefix = str(REPO_ROOT) + os.sep
    for arg in command_args:
        if arg.startswith("/") or arg.startswith(".") or "/" in arg or "\\" in arg:
            resolved_path = os.path.normpath(os.path.join(str(REPO_ROOT), _clean_review_path(arg)))
            if not resolved_path.startswith(allowed_prefix) and resolved_path != str(REPO_ROOT):
                raise ValueError(f"アクセス拒否: {arg} はリポジトリ外です")

    return await _run_review_subprocess(command_name, command_args, str(REPO_ROOT))


review_exec_command = Tool(
    name="execCommand",
    description="リポジトリルート内で許可された汎用コマンドを実行する。利用可能：python、pip、pytest、ls、pwd、mkdir、git、gh。",
    needs_approval=True,
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": '実行するコマンド（例: "pytest -q", "git diff"）'},
        },
        "required": ["command"],
    },
    execute=_review_exec_command_execute,
)


async def _review_get_pull_request_diff_execute(args: dict[str, Any]) -> str:
    pr_number = args["prNumber"]
    if not isinstance(pr_number, int) or pr_number <= 0:
        raise ValueError("prNumber は正の整数で指定してください")
    return await _run_review_subprocess("gh", ["pr", "diff", str(pr_number)], str(REPO_ROOT), timeout=60)


review_get_pull_request_diff = Tool(
    name="getPullRequestDiff",
    description="GitHub CLI を使って指定されたプルリクエストの差分を取得する",
    needs_approval=True,
    parameters={
        "type": "object",
        "properties": {"prNumber": {"type": "number", "description": "差分を取得するプルリクエストの番号"}},
        "required": ["prNumber"],
    },
    execute=_review_get_pull_request_diff_execute,
)


async def _review_create_pull_request_review_execute(args: dict[str, Any]) -> str:
    pr_number = args["prNumber"]
    body = args["body"]
    if not isinstance(pr_number, int) or pr_number <= 0:
        raise ValueError("prNumber は正の整数で指定してください")

    body_file = _write_temp_file(body, "pr-review-body")
    try:
        await _run_review_subprocess(
            "gh", ["pr", "review", str(pr_number), "--comment", "--body-file", body_file], str(REPO_ROOT)
        )
        return "PRレビューを投稿しました"
    finally:
        try:
            os.unlink(body_file)
        except OSError:
            pass


review_create_pull_request_review = Tool(
    name="createPullRequestReview",
    description="GitHub CLI を使って指定されたプルリクエストにレビューコメント（全体コメント）を投稿する",
    needs_approval=True,
    parameters={
        "type": "object",
        "properties": {
            "prNumber": {"type": "number", "description": "レビューを投稿するプルリクエストの番号"},
            "body": {"type": "string", "description": "レビューコメントの本文"},
        },
        "required": ["prNumber", "body"],
    },
    execute=_review_create_pull_request_review_execute,
)


PR_REVIEW_INSTRUCTIONS_TEMPLATE = """{base_instructions}

あなたは GitHub Actions で実行されるコードレビューエージェントです。
あなたの役割は、指定されたプルリクエストの差分（コード変更点）を分析し、コードレビューを行うことです。

## 効率的な実行のためのルール
- ファイルの内容を確認・検索する際は、何度も `grep` や `cat` などのコマンドを実行して一部を探索するのではなく、ファイル全体を `readFile` ツールで一回で読み込み、あなたの能力で内容を検索・把握してください。無駄なコマンド実行によるステップ消費を避けてください。
- レビュー対象の変更差分に直接関係のない、実行環境のライブラリやコード全体の動作について、過度に深掘りして調査することは避けてください。PRの差分レビューに焦点を当て、スマートにTODOリストを完了させてください。

## ワークフロー
以下の手順で作業を進めてください：

1. **TODOリストの作成**:
   - [ ] PRの差分を取得する (getPullRequestDiff)
   - [ ] 差分に含まれるファイルとコード内容を読み込んで理解する (必要に応じて readFile)
   - [ ] 変更内容に対してバグ、改善点、セキュリティ上の問題、または優れた設計についてレビューする
   - [ ] レビュー結果をPRにコメントとして投稿する (createPullRequestReview)

2. **タスクの実行**: TODOリストに従って作業を進める。
   - 変更があったすべてのファイルと内容を詳細に確認してください。
   - テストの追加やドキュメントの更新が抜けていないかもチェックしてください。
   - 指摘は具体的かつ constructive（建設的）に行い、良い実装に対しては褒めるようにしてください。
   - 最後に `createPullRequestReview` を呼び出して、レビューコメント（全体コメント）を投稿してください。

3. **完了報告**: レビューコメントを投稿したら、その内容を要約して結果報告をしてください。
"""


def clean_messages(messages: list[Message]) -> list[Message]:
    """履歴圧縮（manageContext）による API 400 不整合エラーを防ぐための補正。

    providers/clean_messages.py の版と異なり、親の assistant が消えて孤立した
    tool メッセージは「破棄」せず、ダミーの assistant(tool_calls) を補完して整合性を保つ。
    """
    existing_tool_call_ids = {m.tool_call_id for m in messages if m.role == "tool"}

    final_messages: list[Message] = []
    for msg in messages:
        if msg.role == "tool":
            found_assistant = False
            for prev in reversed(final_messages):
                if prev.role == "assistant" and prev.tool_calls:
                    if any(tc.tool_call_id == msg.tool_call_id for tc in prev.tool_calls):
                        found_assistant = True
                        break
            if not found_assistant:
                # 親の assistant が manageContext によって削減されて消えている場合、
                # 親子関係の整合性を保つため、ダミーの assistant (toolCalls) メッセージを自動挿入して補完する
                from src.types import ToolCall

                final_messages.append(
                    Message(
                        role="assistant",
                        content="ツールを実行します。",
                        tool_calls=[ToolCall(tool_call_id=msg.tool_call_id, name=msg.name, args={})],
                    )
                )
            final_messages.append(msg)
        elif msg.role == "assistant" and msg.tool_calls:
            valid_tool_calls = [tc for tc in msg.tool_calls if tc.tool_call_id in existing_tool_call_ids]
            if valid_tool_calls:
                final_messages.append(Message(role="assistant", content=msg.content, tool_calls=valid_tool_calls))
            else:
                final_messages.append(Message(role="assistant", content=msg.content))
        else:
            final_messages.append(msg)

    non_system_messages = [m for m in final_messages if m.role != "system"]
    if not non_system_messages:
        final_messages.append(Message(role="user", content="続けてください。"))

    return final_messages


class _SecureModel:
    """manageContext 後の履歴不整合を吸収してから元のモデルに委譲するラッパー。"""

    def __init__(self, inner: LanguageModel):
        self._inner = inner
        if hasattr(inner, "do_stream"):
            self.do_stream = self._do_stream  # type: ignore[method-assign]

    async def do_generate(self, params):
        from dataclasses import replace

        return await self._inner.do_generate(replace(params, messages=clean_messages(params.messages)))

    async def _do_stream(self, params):
        from dataclasses import replace

        async for chunk in self._inner.do_stream(replace(params, messages=clean_messages(params.messages))):
            yield chunk


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--yolo", action="store_true")
    parser.add_argument("--sandbox", action="store_true")
    return parser.parse_args(argv)


async def _auto_approve(name: str, args: dict) -> bool:
    print(f"[自動承認] ツール {name} の実行を承認しました")
    return True


async def main_async(argv: list[str]) -> int:
    args = parse_args(argv)

    config.sandbox = args.sandbox

    # 1. 環境変数 PULL_REQUEST_NUMBER からPR番号を取得
    pr_number_str = os.environ.get("PULL_REQUEST_NUMBER")
    if not pr_number_str:
        print("エラー: 環境変数 PULL_REQUEST_NUMBER を指定してください", file=sys.stderr)
        return 1
    try:
        pr_number = int(pr_number_str)
    except ValueError:
        pr_number = -1
    if pr_number <= 0:
        print("エラー: PULL_REQUEST_NUMBER は正の整数である必要があります", file=sys.stderr)
        return 1

    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

    base_instructions = load_instructions(str(REPO_ROOT))
    pr_review_instructions = PR_REVIEW_INSTRUCTIONS_TEMPLATE.format(base_instructions=base_instructions)

    provider = os.environ.get("LLM_PROVIDER")
    model_name = os.environ.get("LLM_MODEL")
    api_key = os.environ.get("LLM_API_KEY")

    is_ci = os.environ.get("CI") == "true"

    print("=== Nano Code Reviewer (Python) ===\n")
    print(f"Provider: {provider or '(未設定)'}")
    print(f"Model: {model_name or '(未設定)'}")

    if is_ci:
        print(f"API Key: {_mask_secret(api_key)}")
        if api_key:
            print(f"::add-mask::{api_key}")

    print(f"Workspace: {WORKSPACE_ROOT}")
    print(f"Target PR: #{pr_number}")
    if args.yolo:
        print("[モード] 自動承認モード (--yolo)")
    if config.sandbox:
        print("[モード] サンドボックスモード (--sandbox)")

    if not provider or not model_name or not api_key:
        print("[ERROR] LLM設定が不足しています", file=sys.stderr)
        return 1

    model = create_model_from_env()
    secure_model = _SecureModel(model)

    agent = Agent(
        AgentConfig(
            name="nano-code-reviewer",
            model=secure_model,
            instructions=pr_review_instructions,
            tools={
                "readFile": review_read_file,
                "execCommand": review_exec_command,
                "getPullRequestDiff": review_get_pull_request_diff,
                "createPullRequestReview": review_create_pull_request_review,
            },
            max_steps=60,
            approval_func=(_auto_approve if args.yolo else None),
        )
    )

    try:
        await agent.generate(f"プルリクエスト #{pr_number} のコードレビューを行い、コメントを投稿してください。")

        if is_ci:
            print("\n" + "─" * 60)
            print("[完了] レビューが正常に終了しました")
        return 0
    except Exception as error:  # noqa: BLE001
        print("\n" + "─" * 60, file=sys.stderr)
        print("[ERROR] エージェント実行中にエラーが発生しました\n", file=sys.stderr)

        message = str(error)
        if api_key:
            message = message.replace(api_key, _mask_secret(api_key))
        print(f"原因: {message}", file=sys.stderr)
        return 1


def main() -> None:
    exit_code = asyncio.run(main_async(sys.argv[1:]))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

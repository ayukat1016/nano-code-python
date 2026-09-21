"""ワークスペース内で許可された汎用コマンドを実行するツール。"""
from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Optional

from ..types import Tool

# ワークスペースのルートディレクトリ
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.getcwd(), "workspace"))

# 許可されたコマンド
# 基本ツール: python, ls（基本的な動作確認とファイル一覧）
# 調査・作成系: cat, grep, find, pwd, mkdir（思考ループとコーディング作業で使う）
# Git/GitHub連携: git, gh（ブランチ作成、コミット、プッシュ、PR作成、Issueコメント投稿）
ALLOWED_COMMANDS = ["python", "python3", "pip", "pytest", "ls", "cat", "grep", "find", "pwd", "mkdir", "git", "gh"]

# 出力サイズの上限（文字数）
MAX_OUTPUT_LENGTH = 2048

# 危険な文字の正規表現
DANGEROUS_CHARS = re.compile(r"[;&`$|]")

# 許可コマンド内でも危険なオプション指定は拒否する。
DANGEROUS_PATTERNS = [
    re.compile(r"rm\s+-rf"),
    re.compile(r">\s*/dev"),
    re.compile(r"curl.*\|.*sh"),
    re.compile(r"wget.*\|.*sh"),
    re.compile(r"\s+--git-dir\b"),
    re.compile(r"\s+--work-tree\b"),
    re.compile(r"\s+-exec\b"),
    re.compile(r"\s+-delete\b"),
]


def parse_command(command: str) -> list[str]:
    """簡易的な Bash 互換パーサでコマンド文字列をトークンに分解する。"""
    tokens: list[str] = []
    current = ""
    quote: Optional[str] = None
    escaped = False

    i = 0
    n = len(command)
    while i < n:
        ch = command[i]

        if quote:
            if escaped:
                current += ch
                escaped = False
                i += 1
                continue

            if ch == "\\" and quote == '"':
                escaped = True
                i += 1
                continue

            if ch == quote:
                quote = None
                i += 1
                continue

            current += ch
            i += 1
            continue

        # 引用符のエスケープ以外ではバックスラッシュを保持（Windowsパス対応）
        if ch == "\\":
            next_ch = command[i + 1] if i + 1 < n else None
            if next_ch in ('"', "'"):
                current += next_ch
                i += 2
                continue
            current += ch
            i += 1
            continue

        # クォート開始
        if ch in ('"', "'"):
            quote = ch
            i += 1
            continue

        # 空白で分割
        if ch.isspace():
            if current:
                tokens.append(current)
                current = ""
            i += 1
            continue

        current += ch
        i += 1

    if quote:
        raise ValueError(f"閉じられていない引用符: {quote}")

    if current:
        tokens.append(current)

    return tokens


async def _run_subprocess(command_name: str, command_args: list[str], cwd: str) -> str:
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
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError("コマンドがタイムアウトしました (30秒)")

    stdout = stdout_bytes.decode(errors="replace")
    stderr = stderr_bytes.decode(errors="replace")

    if len(stdout) >= MAX_OUTPUT_LENGTH:
        stdout = stdout[:MAX_OUTPUT_LENGTH] + "\n... (出力が長いため省略されました)"
    if len(stderr) >= MAX_OUTPUT_LENGTH:
        stderr = stderr[:MAX_OUTPUT_LENGTH] + "\n... (出力が長いため省略されました)"

    if proc.returncode == 0:
        # stderrは必ずしもエラーではない（gitはブランチ切替等をstderrに出力する）
        return stdout + (f"\n(stderr: {stderr.strip()})" if stderr else "")

    # コマンド失敗時 (returncode != 0) に例外を送出することで、
    # 呼び出し元のエージェントが失敗を認識し、自律的に回復・修正行動を取れるようにしている。
    raise RuntimeError(f"コマンドが異常終了しました (exit code: {proc.returncode})\n{stderr}")


async def exec_command_execute(args: dict[str, Any]) -> str:
    command_name = ""
    command_args: list[str] = []
    command_for_check = ""

    if isinstance(args.get("command"), str):
        command = args["command"]
        # 1. 危険文字チェック
        if DANGEROUS_CHARS.search(command):
            raise ValueError("セキュリティ上の理由により、シェルメタ文字を含むコマンドは実行できません")

        # 2. コマンドの解析
        parts = parse_command(command)
        command_name = parts[0] if parts else ""
        command_args = parts[1:]
        command_for_check = command
    elif isinstance(args.get("commandName"), str):
        command_name = args["commandName"]
        raw_args = args.get("commandArgs")
        if raw_args is not None:
            if not isinstance(raw_args, list) or not all(isinstance(a, str) for a in raw_args):
                raise ValueError("commandArgs は文字列配列で指定してください")
            command_args = list(raw_args)
        command_for_check = " ".join([command_name, *command_args])
    else:
        raise ValueError("command または commandName を指定してください")

    if not command_name:
        raise ValueError("コマンドが空です")

    # 3. ホワイトリストチェック
    if command_name not in ALLOWED_COMMANDS:
        raise ValueError(f"コマンド {command_name} は許可されていません")

    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(command_for_check):
            raise ValueError("危険なコマンドパターンが検出されました")

    # 4. パス引数の検証（ワークスペース内かチェック）
    allowed_prefix = WORKSPACE_ROOT + os.sep
    for arg in command_args:
        # パスが '/' や '.' で始まる場合のトラバーサル漏れを防ぐためのセキュリティガード拡張。
        if arg.startswith("/") or arg.startswith(".") or "/" in arg or "\\" in arg:
            resolved_path = os.path.normpath(os.path.join(WORKSPACE_ROOT, arg))
            if not resolved_path.startswith(allowed_prefix) and resolved_path != WORKSPACE_ROOT:
                raise ValueError(f"アクセス拒否: {arg} はワークスペース外です")

    # 5. shell=False で実行（コマンドインジェクション対策）
    return await _run_subprocess(command_name, command_args, WORKSPACE_ROOT)


exec_command = Tool(
    name="execCommand",
    description=(
        "ワークスペース内で許可された汎用コマンドを実行する。"
        "利用可能：python、pip、pytest、ls、cat、grep、find、pwd、mkdir、git、gh。"
    ),
    # ツール実行時に人間の承認が必要かどうか
    needs_approval=True,
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": '実行するコマンド（例: "pytest -q", "ls -la src/"）',
            }
        },
        "required": ["command"],
    },
    execute=exec_command_execute,
)

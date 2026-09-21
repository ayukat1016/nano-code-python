"""bwrap サンドボックス対応版の execCommand ツール。"""
from __future__ import annotations

import os
import re
import sys
from typing import Any

from ..config import config
from ..types import Tool
from .exec_command import (
    DANGEROUS_PATTERNS,
    WORKSPACE_ROOT,
    _run_subprocess,
    parse_command,
)
from ..core.sandbox import Sandbox, SandboxOptions

ALLOWED_COMMANDS = ["python", "python3", "pip", "pytest", "ls", "cat", "grep", "find", "pwd", "mkdir", "git", "gh"]

DANGEROUS_CHARS = re.compile(r"[;&`$|]")

# 環境変数はホワイトリスト方式（機密情報の漏洩防止）
SAFE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "HOME": "/tmp",
    "LANG": os.environ.get("LANG", "C.UTF-8"),
}


# Git/GitHub ツールから安全に引数配列を渡せるよう、commandName / commandArgs 形式も受け付ける。
async def exec_command_sandbox_execute(args: dict[str, Any]) -> str:
    command_name = ""
    command_args: list[str] = []
    command_for_check = ""

    if isinstance(args.get("command"), str):
        command = args["command"]
        if DANGEROUS_CHARS.search(command):
            raise ValueError("シェルメタ文字を含むコマンドは実行できません")
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

    if command_name not in ALLOWED_COMMANDS:
        raise ValueError(f"コマンド {command_name} は許可されていません")

    # サンドボックス無効時でも危険なオプション指定を早めに拒否する。
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(command_for_check):
            raise ValueError("危険なコマンドパターンが検出されました")

    allowed_prefix = WORKSPACE_ROOT + os.sep
    for arg in command_args:
        if arg.startswith("/") or arg.startswith(".") or "/" in arg or "\\" in arg:
            resolved_path = os.path.normpath(os.path.join(WORKSPACE_ROOT, arg))
            if not resolved_path.startswith(allowed_prefix) and resolved_path != WORKSPACE_ROOT:
                raise ValueError(f"アクセス拒否: {arg} はワークスペース外です")

    # サンドボックス分岐
    if sys.platform == "linux" and config.sandbox:
        sandbox = Sandbox()
        result = await sandbox.run(
            command_name,
            command_args,
            SandboxOptions(allow_network=False, env=SAFE_ENV),
        )
        if result.exit_code != 0:
            raise RuntimeError(f"Command failed: {result.stderr}")
        return result.stdout

    # 通常実行（サンドボックス無効時）
    return await _run_subprocess(command_name, command_args, WORKSPACE_ROOT)


exec_command_sandbox = Tool(
    name="execCommand",
    description="ワークスペース内で許可されたコマンドを実行",
    needs_approval=True,
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "実行するコマンド"},
        },
        "required": ["command"],
    },
    execute=exec_command_sandbox_execute,
)

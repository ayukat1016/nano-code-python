"""ワークスペース内にファイルを作成・上書きするツール。"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from ..types import Tool

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.getcwd(), "workspace"))


def _write_file_sync(path: str, content: str) -> str:
    # ステップ1: 相対パスを絶対パスに変換
    absolute_path = os.path.normpath(os.path.join(WORKSPACE_ROOT, path))

    # ステップ2: ワークスペース内かチェック（ディレクトリトラバーサル対策）
    allowed_prefix = WORKSPACE_ROOT + os.sep
    if not absolute_path.startswith(allowed_prefix) and absolute_path != WORKSPACE_ROOT:
        raise ValueError(f"アクセス拒否: {path} はワークスペース外です")

    # シンボリックリンク経由のトラバーサルを防ぐため、実体パスも検証する。
    # 新規作成時は、存在する親ディレクトリまで遡って確認する。
    check_path = absolute_path
    while check_path != WORKSPACE_ROOT:
        if os.path.exists(check_path) or os.path.islink(check_path):
            real_path = os.path.realpath(check_path)
            if not real_path.startswith(allowed_prefix) and real_path != WORKSPACE_ROOT:
                raise ValueError(f"アクセス拒否: {path} はシンボリックリンク経由でワークスペース外を参照しています")
            break
        parent = os.path.dirname(check_path)
        if parent == check_path:
            break
        check_path = parent

    # ステップ3: ディレクトリの作成（存在しない場合）
    os.makedirs(os.path.dirname(absolute_path), exist_ok=True)

    # ステップ4: ファイルの書き込み
    with open(absolute_path, "w", encoding="utf-8") as f:
        f.write(content)

    return f"ファイルを書き込みました: {path}"


async def _write_file_execute(args: dict[str, Any]) -> str:
    return await asyncio.to_thread(_write_file_sync, args["path"], args["content"])


write_file = Tool(
    name="writeFile",
    description="指定されたパスにファイルを作成または上書きする。ディレクトリが存在しない場合は自動的に作成される。",
    # ツール実行時に人間の承認が必要かどうか
    needs_approval=True,
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "書き込むファイルのパス"},
            "content": {"type": "string", "description": "ファイルに書き込む内容"},
        },
        "required": ["path", "content"],
    },
    execute=_write_file_execute,
)

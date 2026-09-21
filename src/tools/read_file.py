"""ワークスペース内のファイルを読み込むツール。"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from ..types import Tool

# ワークスペースのルートディレクトリを定義
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.getcwd(), "workspace"))

# 読み込み可能なファイルサイズの上限（LLMのコンテキストウィンドウ保護）
MAX_FILE_SIZE = 100 * 1024  # 100KB


def _read_file_sync(path: str) -> str:
    # ステップ1: 相対パスを絶対パスに変換
    absolute_path = os.path.normpath(os.path.join(WORKSPACE_ROOT, path))

    # ステップ2: ワークスペース内かチェック（ディレクトリトラバーサル対策）
    allowed_prefix = WORKSPACE_ROOT + os.sep
    if not absolute_path.startswith(allowed_prefix) and absolute_path != WORKSPACE_ROOT:
        raise ValueError(f"アクセス拒否: {path} はワークスペース外です")

    # ステップ3: シンボリックリンクを解決して実パスを検証
    try:
        real_path = os.path.realpath(absolute_path, strict=True)
    except FileNotFoundError as error:
        raise ValueError(f"ファイルが見つかりません: {path}") from error

    if not real_path.startswith(allowed_prefix) and real_path != WORKSPACE_ROOT:
        raise ValueError(f"アクセス拒否: {path} はシンボリックリンク経由でワークスペース外を参照しています")

    # ステップ4: ファイル種別とサイズのチェック
    try:
        stat = os.stat(absolute_path)
    except FileNotFoundError as error:
        raise ValueError(f"ファイルが見つかりません: {path}") from error

    if not os.path.isfile(absolute_path):
        raise ValueError(f"通常ファイルではありません: {path}")
    if stat.st_size > MAX_FILE_SIZE:
        raise ValueError(
            f"ファイルが大きすぎます: {path} ({round(stat.st_size / 1024)}KB)。"
            f"100KB以下のファイルのみ読み込めます。"
        )

    # ステップ5: ファイルの読み込み
    with open(absolute_path, "r", encoding="utf-8") as f:
        return f.read()


async def _read_file_execute(args: dict[str, Any]) -> str:
    return await asyncio.to_thread(_read_file_sync, args["path"])


read_file = Tool(
    name="readFile",
    description=(
        "ワークスペース内の指定されたパスのファイル内容を文字列として読み込む。"
        "ファイルが存在しない場合はエラーを返す。100KBを超える巨大ファイルは読み込めない"
        "（コンテキストウィンドウ保護のため）。相対パスまたは絶対パスを指定できる。"
    ),
    # ツール実行時に人間の承認が必要かどうか
    needs_approval=False,
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "読み込むファイルのパス（例: 'README.md', 'src/index.py'）",
            }
        },
        "required": ["path"],
    },
    execute=_read_file_execute,
)

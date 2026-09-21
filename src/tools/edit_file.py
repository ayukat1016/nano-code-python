"""ファイルの一部を検索・置換するツール。"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from ..types import Tool

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.getcwd(), "workspace"))


def _edit_file_sync(path: str, old_text: str, new_text: str) -> str:
    # ステップ1: 相対パスを絶対パスに変換
    absolute_path = os.path.normpath(os.path.join(WORKSPACE_ROOT, path))

    # ステップ2: ワークスペース内かチェック（ディレクトリトラバーサル対策）
    allowed_prefix = WORKSPACE_ROOT + os.sep
    if not absolute_path.startswith(allowed_prefix) and absolute_path != WORKSPACE_ROOT:
        raise ValueError(f"アクセス拒否: {path} はワークスペース外です")

    # シンボリックリンク経由のトラバーサルを防ぐため、実体パスも検証する。
    try:
        real_path = os.path.realpath(absolute_path, strict=True)
    except FileNotFoundError as error:
        raise ValueError(f"ファイルが見つかりません: {path}") from error

    if not real_path.startswith(allowed_prefix) and real_path != WORKSPACE_ROOT:
        raise ValueError(f"アクセス拒否: {path} はシンボリックリンク経由でワークスペース外を参照しています")

    # ステップ3: ファイルを読み込む
    with open(absolute_path, "r", encoding="utf-8") as f:
        content = f.read()

    # ステップ4: あいまい性チェック（変更対象が一意に特定できるか確認）
    matches = content.count(old_text)
    if matches == 0:
        preview = old_text if len(old_text) <= 50 else f"{old_text[:50]}..."
        raise ValueError(f"変更対象が見つかりません: {preview}")
    if matches > 1:
        raise ValueError(f"複数の候補が見つかりました（{matches}箇所）。より具体的な範囲を指定してください")

    # ステップ5: テキストを検索・置換して書き込み
    new_content = content.replace(old_text, new_text, 1)
    with open(absolute_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    return f"ファイルを編集しました: {old_text[:30]}... → {new_text[:30]}..."


async def _edit_file_execute(args: dict[str, Any]) -> str:
    return await asyncio.to_thread(_edit_file_sync, args["path"], args["oldText"], args["newText"])


edit_file = Tool(
    name="editFile",
    description=(
        "ファイルの一部を編集する。oldTextで指定した箇所をnewTextに置き換える。"
        "oldTextが複数見つかる場合はエラーを返すため、一意に特定できる範囲を指定すること。"
        "ファイル全体を読み書きするよりトークン消費が少ない。"
    ),
    # ツール実行時に人間の承認が必要かどうか
    needs_approval=True,
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "編集するファイルのパス"},
            "oldText": {"type": "string", "description": "変更前のテキスト（一意に特定できる範囲を指定）"},
            "newText": {"type": "string", "description": "変更後のテキスト"},
        },
        "required": ["path", "oldText", "newText"],
    },
    execute=_edit_file_execute,
)

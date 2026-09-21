"""Git 操作用ツール（ブランチ作成・コミット・プッシュ）。"""
from __future__ import annotations

import os
import re
import time
from typing import Any

from ..types import Tool
from .exec_command import exec_command

WORKSPACE_ROOT = os.path.join(os.getcwd(), "workspace")

_BRANCH_NAME_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def _validate_branch_name(name: str) -> None:
    """CLI 引数として安全に渡せる Git ref に絞る。"""
    if not name or len(name) > 120:
        raise ValueError("ブランチ名が不正です")
    if name.startswith("-") or name.startswith(":"):
        raise ValueError("ブランチ名の先頭に - や : は使えません")
    if re.search(r"\s", name):
        raise ValueError("ブランチ名に空白は使えません")
    if not _BRANCH_NAME_RE.match(name):
        raise ValueError("ブランチ名に使用できない文字が含まれています")
    if ".." in name or "//" in name or name.endswith("/") or name.endswith("."):
        raise ValueError("ブランチ名形式が不正です")


def _validate_file_path(file_path: str) -> None:
    """`git add -- <file>` に分けて渡せるよう、ファイルパスを最低限検証する。"""
    if not file_path:
        raise ValueError("ファイルパスが空です")
    if file_path.startswith("-"):
        raise ValueError("ファイルパスの先頭に - は使えません")
    if re.search(r"[\r\n\0]", file_path):
        raise ValueError("ファイルパスに不正な制御文字が含まれています")


def _write_temp_file(content: str, prefix: str) -> str:
    """引用符や改行を含むメッセージも扱えるよう、一時ファイル経由で渡す。"""
    os.makedirs(WORKSPACE_ROOT, exist_ok=True)
    temp_path = os.path.join(WORKSPACE_ROOT, f".{prefix}-{int(time.time() * 1000)}.txt")
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(content)
    return temp_path


async def _create_branch_execute(args: dict[str, Any]) -> str:
    branch_name = args["branchName"]
    _validate_branch_name(branch_name)
    try:
        result = await exec_command.execute(
            {"commandName": "git", "commandArgs": ["checkout", "-B", branch_name]}
        )
        return f"ブランチを作成しました: {branch_name}\n{result}"
    except Exception as error:
        raise RuntimeError(f"ブランチ作成失敗: {error}") from error


create_branch = Tool(
    name="createBranch",
    description="新しいGitブランチを作成。既存ブランチがある場合は強制リセット",
    needs_approval=True,
    parameters={
        "type": "object",
        "properties": {
            "branchName": {"type": "string", "description": "作成するブランチ名（例: 'fix/error-handling'）"}
        },
        "required": ["branchName"],
    },
    execute=_create_branch_execute,
)


async def _commit_execute(args: dict[str, Any]) -> str:
    message = args["message"]
    files = args["files"]

    if not message or "\0" in message:
        raise ValueError("コミットメッセージが不正です")

    try:
        status = await exec_command.execute({"commandName": "git", "commandArgs": ["status", "--porcelain"]})

        if not status.strip():
            return "コミットする変更がありません（既に最新の状態です）"

        for file in files:
            _validate_file_path(file)
            await exec_command.execute({"commandName": "git", "commandArgs": ["add", "--", file]})

        message_file = _write_temp_file(message, "commit-message")
        try:
            result = await exec_command.execute({"commandName": "git", "commandArgs": ["commit", "-F", message_file]})
            return f"コミットしました: {message}\n{result}"
        finally:
            try:
                os.unlink(message_file)
            except OSError:
                pass
    except Exception as error:
        raise RuntimeError(f"コミット失敗: {error}") from error


commit = Tool(
    name="commit",
    description="変更をコミット",
    needs_approval=True,
    parameters={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "コミットメッセージ"},
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "コミットするファイルのパスのリスト",
            },
        },
        "required": ["message", "files"],
    },
    execute=_commit_execute,
)


async def _push_branch_execute(args: dict[str, Any]) -> str:
    branch_name = args["branchName"]
    _validate_branch_name(branch_name)
    try:
        result = await exec_command.execute(
            {"commandName": "git", "commandArgs": ["push", "-u", "origin", branch_name]}
        )
        return f"ブランチをプッシュしました: {branch_name}\n{result}"
    except Exception as error:
        raise RuntimeError(f"プッシュ失敗: {error}") from error


push_branch = Tool(
    name="pushBranch",
    description="ブランチをリモートにプッシュ",
    needs_approval=True,
    parameters={
        "type": "object",
        "properties": {"branchName": {"type": "string", "description": "プッシュするブランチ名"}},
        "required": ["branchName"],
    },
    execute=_push_branch_execute,
)

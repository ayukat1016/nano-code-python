"""GitHub CLI (gh) を使った PR 作成・Issue コメント投稿ツール。"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from ..types import Tool
from .exec_command import exec_command

WORKSPACE_ROOT = os.path.join(os.getcwd(), "workspace")

_BRANCH_NAME_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def _validate_branch_name(name: str) -> None:
    """gh コマンドの引数として安全に渡せる Git ref に絞る。"""
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


def _validate_title(title: str) -> None:
    """PR タイトルを gh の --title 引数として渡せる形に制限する。"""
    if not title or len(title) > 200:
        raise ValueError("PRタイトルが不正です")
    if re.search(r"[\r\n\0]", title):
        raise ValueError("PRタイトルに改行や制御文字は使えません")


def _write_temp_file(content: str, prefix: str) -> str:
    os.makedirs(WORKSPACE_ROOT, exist_ok=True)
    temp_path = os.path.join(WORKSPACE_ROOT, f".{prefix}-{int(time.time() * 1000)}.txt")
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(content)
    return temp_path


async def _create_pull_request_execute(args: dict[str, Any]) -> str:
    title = args["title"]
    body = args["body"]
    head = args["head"]
    base = args["base"]

    _validate_title(title)
    _validate_branch_name(head)
    _validate_branch_name(base)

    list_result = await exec_command.execute(
        {
            "commandName": "gh",
            "commandArgs": [
                "pr", "list", "--head", head, "--base", base, "--state", "open", "--json", "number",
            ],
        }
    )

    body_file = _write_temp_file(body, "pr-body")

    try:
        try:
            existing_prs = json.loads(list_result or "[]")
        except json.JSONDecodeError:
            existing_prs = None

        if isinstance(existing_prs, list) and existing_prs:
            pr_number = str(existing_prs[0]["number"])
            await exec_command.execute(
                {"commandName": "gh", "commandArgs": ["pr", "edit", pr_number, "--body-file", body_file]}
            )
            return f"既存のPR #{pr_number} を更新しました"

        result = await exec_command.execute(
            {
                "commandName": "gh",
                "commandArgs": [
                    "pr", "create", "--title", title, "--body-file", body_file, "--base", base, "--head", head,
                ],
            }
        )
        return f"PRを作成しました: {result}"
    finally:
        try:
            os.unlink(body_file)
        except OSError:
            pass


create_pull_request = Tool(
    name="createPullRequest",
    description="ghコマンドを使ってPRを作成する。既存PRがあれば更新",
    needs_approval=True,
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "PRのタイトル"},
            "body": {"type": "string", "description": "PRの本文"},
            "head": {"type": "string", "description": "マージ元のブランチ名（例: 'fix/error-handling'）"},
            "base": {"type": "string", "description": "マージ先のブランチ名（通常は 'main'）"},
        },
        "required": ["title", "body", "head", "base"],
    },
    execute=_create_pull_request_execute,
)


async def _create_issue_comment_execute(args: dict[str, Any]) -> str:
    issue_number = args["issueNumber"]
    body = args["body"]

    if not isinstance(issue_number, int) or issue_number <= 0:
        raise ValueError("issueNumber は正の整数で指定してください")

    body_file = _write_temp_file(body, "comment-body")
    try:
        await exec_command.execute(
            {"commandName": "gh", "commandArgs": ["issue", "comment", str(issue_number), "--body-file", body_file]}
        )
        return "コメントを投稿しました"
    finally:
        try:
            os.unlink(body_file)
        except OSError:
            pass


create_issue_comment = Tool(
    name="createIssueComment",
    description="Issueにコメントを投稿する",
    needs_approval=True,
    parameters={
        "type": "object",
        "properties": {
            "issueNumber": {"type": "number", "description": "コメントするIssueの番号"},
            "body": {"type": "string", "description": "コメントの本文"},
        },
        "required": ["issueNumber", "body"],
    },
    execute=_create_issue_comment_execute,
)

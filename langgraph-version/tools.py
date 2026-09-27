"""LangChainの@toolデコレータで実装した基本ツール群。

src/tools/{read_file,write_file,edit_file}.py と同じ役割（ワークスペース内への
アクセス制限）を持たせつつ、LangChain/LangGraphの流儀（@tool）で書き直したもの。
"""
from __future__ import annotations

import os
import subprocess

from langchain_core.tools import tool

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "workspace"))
MAX_FILE_SIZE = 100 * 1024

# 承認が必要なツール名の集合。src/types.py の Tool.needs_approval に相当する情報を
# LangChainの@toolには持たせられないため、ここで別管理する。
TOOLS_NEEDING_APPROVAL = {"writeFile", "editFile", "execCommand"}


def _resolve(path: str) -> str:
    absolute_path = os.path.normpath(os.path.join(WORKSPACE_ROOT, path))
    allowed_prefix = WORKSPACE_ROOT + os.sep
    if not absolute_path.startswith(allowed_prefix) and absolute_path != WORKSPACE_ROOT:
        raise ValueError(f"アクセス拒否: {path} はワークスペース外です")
    return absolute_path


@tool(name_or_callable="readFile")
def read_file(path: str) -> str:
    """ワークスペース内の指定されたパスのファイル内容を文字列として読み込む。100KBを超えるファイルは読み込めない。"""
    absolute_path = _resolve(path)
    real_path = os.path.realpath(absolute_path)
    allowed_prefix = WORKSPACE_ROOT + os.sep
    if not real_path.startswith(allowed_prefix) and real_path != WORKSPACE_ROOT:
        raise ValueError(f"アクセス拒否: {path} はシンボリックリンク経由でワークスペース外を参照しています")
    if not os.path.isfile(real_path):
        raise ValueError(f"ファイルが見つかりません: {path}")
    if os.path.getsize(real_path) > MAX_FILE_SIZE:
        raise ValueError(f"ファイルが大きすぎます: {path}")
    with open(real_path, "r", encoding="utf-8") as f:
        return f.read()


@tool(name_or_callable="writeFile")
def write_file(path: str, content: str) -> str:
    """指定されたパスにファイルを作成または上書きする。ディレクトリが存在しない場合は自動的に作成される。"""
    absolute_path = _resolve(path)
    os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
    with open(absolute_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"ファイルを書き込みました: {path}"


@tool(name_or_callable="editFile")
def edit_file(path: str, old_text: str, new_text: str) -> str:
    """ファイルの一部を編集する。old_textで指定した箇所をnew_textに置き換える（一意に特定できる必要がある）。"""
    absolute_path = _resolve(path)
    with open(absolute_path, "r", encoding="utf-8") as f:
        content = f.read()
    matches = content.count(old_text)
    if matches == 0:
        raise ValueError(f"変更対象が見つかりません: {old_text[:50]}")
    if matches > 1:
        raise ValueError(f"複数の候補が見つかりました（{matches}箇所）")
    with open(absolute_path, "w", encoding="utf-8") as f:
        f.write(content.replace(old_text, new_text, 1))
    return f"ファイルを編集しました: {path}"


@tool(name_or_callable="execCommand")
def exec_command(command: str) -> str:
    """ワークスペース内で許可されたコマンドを実行する（python, pip, pytest, ls, cat のみ）。"""
    allowed = {"python", "python3", "pip", "pytest", "ls", "cat"}
    parts = command.split()
    if not parts or parts[0] not in allowed:
        raise ValueError(f"コマンド {parts[0] if parts else ''} は許可されていません")
    result = subprocess.run(
        parts, cwd=WORKSPACE_ROOT, capture_output=True, text=True, timeout=30
    )
    output = result.stdout + (f"\n(stderr: {result.stderr})" if result.stderr else "")
    if result.returncode != 0:
        raise RuntimeError(f"コマンドが異常終了しました (exit code: {result.returncode})\n{result.stderr}")
    return output


ALL_TOOLS = [read_file, write_file, edit_file, exec_command]

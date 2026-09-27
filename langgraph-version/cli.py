#!/usr/bin/env python3
"""LangGraph版 nano-code の CLIエントリポイント。

使用法:
    python cli.py "タスク内容" [--yolo]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT.parent / ".env")

from langgraph.types import Command  # noqa: E402

from agent import build_graph  # noqa: E402
from model_factory import create_model_from_env  # noqa: E402

BASE_SYSTEM_PROMPT = """あなたはPythonのコーディングアシスタントです。
既存ファイルを編集する際は、writeFileではなくeditFileを優先的に使ってください。
作業を始める前に、必ずTODOリストを作成し、各項目を完了したら報告してください。
"""


def load_instructions() -> str:
    """src/core/prompt.py の load_instructions と同じく、workspace/AGENTS.md が
    あればプロジェクト固有の指示としてベースプロンプトに追記する。"""
    agents_md_path = REPO_ROOT / "workspace" / "AGENTS.md"
    if agents_md_path.exists():
        agents_md = agents_md_path.read_text(encoding="utf-8")
        return f"{BASE_SYSTEM_PROMPT}\n\n# プロジェクト固有の指示\n\n{agents_md}"
    return BASE_SYSTEM_PROMPT


def ask_approval(tool_name: str, args: dict) -> bool:
    print("\n--- 承認が必要です ---")
    print(f"ツール: {tool_name}")
    print(f"引数: {json.dumps(args, ensure_ascii=False, indent=2)}")
    answer = input("このツールを実行しますか？ (y/n): ")
    if answer.strip().lower() == "y":
        print("承認されました。実行します...\n")
        return True
    print("キャンセルされました。\n")
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task", nargs="*", help="タスク内容")
    parser.add_argument("--yolo", action="store_true", help="自動承認モード")
    args = parser.parse_args()

    user_prompt = " ".join(args.task)
    if not user_prompt:
        print("エラー: タスク内容を指定してください", file=sys.stderr)
        print('使用法: python cli.py "タスク内容" [--yolo]', file=sys.stderr)
        return 1

    os.makedirs(REPO_ROOT / "workspace", exist_ok=True)

    model = create_model_from_env()
    graph = build_graph(model)
    config = {"configurable": {"thread_id": "cli-session"}, "recursion_limit": 60}

    print("=== Nano Code Agent (LangGraph版) ===\n")
    print(f"Task: {user_prompt}\n")

    inputs = {"messages": [("system", load_instructions()), ("user", user_prompt)]}

    while True:
        result = graph.invoke(inputs, config=config)

        # __interrupt__ があれば、承認ゲートで一時停止している。
        pending_interrupts = result.get("__interrupt__")
        if not pending_interrupts:
            break

        interrupt_obj = pending_interrupts[0]
        payload = interrupt_obj.value
        approved = True if args.yolo else ask_approval(payload["tool"], payload["args"])
        if args.yolo:
            print(f"[自動承認] ツール {payload['tool']} の実行を承認しました")

        inputs = Command(resume=approved)

    final_message = result["messages"][-1]
    print("\n" + "─" * 60)
    print(final_message.content)
    return 0


if __name__ == "__main__":
    sys.exit(main())

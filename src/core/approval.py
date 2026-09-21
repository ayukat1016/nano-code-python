"""ツール実行前の対話的な承認プロンプト。"""
from __future__ import annotations

import asyncio
import json
from typing import Any


async def request_approval(tool_name: str, args: dict[str, Any]) -> bool:
    def ask() -> bool:
        print("\n--- 承認が必要です ---")
        print(f"ツール: {tool_name}")
        print(f"引数: {json.dumps(args, ensure_ascii=False, indent=2)}")

        answer = input("このツールを実行しますか？ (y/n): ")
        if answer.strip().lower() == "y":
            print("承認されました。実行します...\n")
            return True
        print("キャンセルされました。\n")
        return False

    # input() はブロッキング呼び出しのため、イベントループを止めないよう別スレッドで実行する
    return await asyncio.to_thread(ask)

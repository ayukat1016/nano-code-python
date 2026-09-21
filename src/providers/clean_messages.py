"""履歴圧縮後も、ツール呼び出しと結果の対応が壊れないように補正するヘルパー。

各プロバイダ（anthropic / openai / google）が API に送信する直前に呼び出す。
親の assistant メッセージが消えて孤立した tool メッセージは破棄し、
子の tool メッセージが消えて孤立した tool_calls はその呼び出しだけを取り除く。
"""
from __future__ import annotations

from ..types import Message


def clean_messages(messages: list[Message]) -> list[Message]:
    existing_tool_call_ids = {m.tool_call_id for m in messages if m.role == "tool"}

    final_messages: list[Message] = []
    for msg in messages:
        if msg.role == "tool":
            found_assistant = False
            for prev in reversed(final_messages):
                if prev.role == "assistant" and prev.tool_calls:
                    if any(tc.tool_call_id == msg.tool_call_id for tc in prev.tool_calls):
                        found_assistant = True
                        break
            if found_assistant:
                final_messages.append(msg)
        elif msg.role == "assistant" and msg.tool_calls:
            valid_tool_calls = [tc for tc in msg.tool_calls if tc.tool_call_id in existing_tool_call_ids]
            if valid_tool_calls:
                final_messages.append(Message(role="assistant", content=msg.content, tool_calls=valid_tool_calls))
            else:
                final_messages.append(Message(role="assistant", content=msg.content))
        else:
            final_messages.append(msg)

    # system メッセージを除いた結果が空になるのを防ぐ
    non_system_messages = [m for m in final_messages if m.role != "system"]
    if not non_system_messages:
        final_messages.append(Message(role="user", content="続けてください。"))

    return final_messages

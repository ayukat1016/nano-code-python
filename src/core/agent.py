"""コーディングエージェント本体（思考ループ）。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from ..types import LanguageModel, Message, Tool
from .approval import request_approval
from .generate_stream import collect_stream_result
from .generate_text import generate_text

ApprovalFunc = Callable[[str, dict[str, Any]], Awaitable[bool]]

# コンテキスト管理の簡易的な制限：文字数で判定
# （例: 30,000文字 ≈ 10k~15kトークン程度と仮定。使用するモデルのコンテキストウィンドウに合わせて調整）
CHAR_LIMIT = 30000


@dataclass
class AgentConfig:
    name: str  # エージェント名
    instructions: str  # システム指示
    model: LanguageModel  # 使用するモデル
    tools: dict[str, Tool] = field(default_factory=dict)  # 利用可能なツール
    max_steps: int = 10  # 最大実行ステップ数
    verbose: bool = False  # 詳細ログ出力フラグ
    approval_func: Optional[ApprovalFunc] = None  # 承認関数
    use_streaming: bool = False  # ストリーミング機能との互換性のためのフラグ


async def _execute_tool(tool: Tool, args: dict[str, Any]) -> str:
    try:
        return await tool.execute(args)
    except Exception as error:  # 例外をキャッチし、エラーメッセージを返す（例外をスローしない）
        return f"エラー: {error}"


class Agent:
    def __init__(self, config: AgentConfig):
        self.name = config.name
        self.instructions = config.instructions
        self.model = config.model
        # 辞書形式から配列に変換
        self.tools: list[Tool] = list(config.tools.values())
        self.max_steps = config.max_steps
        self.verbose = config.verbose
        # approval_func が渡されなければデフォルトの対話的承認を使用
        self.approval_func: ApprovalFunc = config.approval_func or request_approval
        self.use_streaming = config.use_streaming

    async def generate(self, user_prompt: str) -> dict[str, str]:
        # ステップ1：会話ループの開始
        messages: list[Message] = [
            Message(role="system", content=self.instructions),
            Message(role="user", content=user_prompt),
        ]

        current_step = 0
        final_text = ""
        tool_call_count = 0

        while current_step < self.max_steps:
            current_step += 1

            if self.verbose:
                print(f"\n=== ステップ {current_step}/{self.max_steps} ===")

            # コンテキスト管理
            messages = self._manage_context(messages)

            model_can_stream = hasattr(self.model, "do_stream")

            # ストリーミング機能が有効で、かつモデルがストリーミングに対応している場合はストリーミングを使用
            if self.use_streaming and model_can_stream:
                def on_chunk(chunk: Any) -> None:
                    if chunk.kind == "delta" and chunk.text:
                        print(chunk.text, end="", flush=True)

                response = await collect_stream_result(
                    self.model, messages, tools=self.tools, on_chunk=on_chunk
                )
                print()  # 改行
            else:
                if self.use_streaming:
                    print("警告: モデルがストリーミングに対応していないため、通常生成を使用します")
                response = await generate_text(self.model, messages, tools=self.tools)

            # テキスト応答の保存と出力
            if response.text:
                final_text = response.text
                # ストリーミング時はすでに逐次出力されているため、非ストリーミング時のみ出力
                if not (self.use_streaming and model_can_stream):
                    print(response.text)

            # ステップ2：ツール実行
            if response.tool_calls:
                messages.append(
                    Message(role="assistant", content=response.text, tool_calls=response.tool_calls)
                )

                for tool_call in response.tool_calls:
                    tool = next((t for t in self.tools if t.name == tool_call.name), None)

                    if tool is None:
                        # ツールが見つからない場合
                        messages.append(
                            Message(
                                role="tool",
                                tool_call_id=tool_call.tool_call_id,
                                name=tool_call.name,
                                content=f"エラー: ツール {tool_call.name} が見つかりません",
                            )
                        )
                        continue

                    if self.verbose:
                        print(f"[ツール実行] {tool_call.name}({json.dumps(tool_call.args, ensure_ascii=False)})")

                    # ステップ3：承認チェック
                    if tool.needs_approval:
                        approved = await self.approval_func(tool_call.name, tool_call.args)
                        if not approved:
                            messages.append(
                                Message(
                                    role="tool",
                                    tool_call_id=tool_call.tool_call_id,
                                    name=tool_call.name,
                                    content="ユーザーによってキャンセルされました。別の方法を検討してください。",
                                )
                            )
                            continue

                    # ツールを実行
                    result = await _execute_tool(tool, tool_call.args)
                    tool_call_count += 1

                    if self.verbose:
                        preview = result[:200] + ("..." if len(result) > 200 else "")
                        print(f"[結果] {preview}")

                    messages.append(
                        Message(
                            role="tool",
                            tool_call_id=tool_call.tool_call_id,
                            name=tool_call.name,
                            content=result,
                        )
                    )

                continue  # 次のループへ

            # ツール呼び出しがない場合は完了（会話履歴への追加）
            messages.append(Message(role="assistant", content=response.text))
            break

        # ループ終了後のチェック
        if current_step >= self.max_steps:
            print("警告: 最大ステップ数に達しました")

        # ツール未使用で終了した場合の警告
        if tool_call_count == 0 and current_step == 1:
            print("警告: ツールが一度も使用されずに終了しました")

        return {"text": final_text}

    def _manage_context(self, messages: list[Message]) -> list[Message]:
        total_length = sum(len(m.content or "") for m in messages)

        # 制限内なら何もしない
        if total_length < CHAR_LIMIT:
            return messages

        print(f"\n[Context] 会話履歴を圧縮します (現在: {total_length}文字)")

        # 1. 守るべきメッセージを確保
        # 先頭（システムプロンプト）
        system_message = messages[0]
        # 最新の4メッセージ（直近の文脈）
        recent_messages = messages[-4:]
        # 圧縮対象となる中間メッセージ
        middle_messages = messages[1:-4]

        # 2. 戦略A: 古いツール実行結果を「省略」に置換
        # readFileの結果などが巨大になりがちなので、これを削るのが最も効果的
        def maybe_omit(msg: Message) -> Message:
            if msg.role == "tool" and len(msg.content or "") > 200:
                return Message(
                    role=msg.role,
                    content=f"(以前のツール実行結果は省略されました: {len(msg.content)}文字)",
                    tool_call_id=msg.tool_call_id,
                    name=msg.name,
                )
            return msg

        middle_messages = [maybe_omit(m) for m in middle_messages]

        # 3. 戦略B: それでも溢れるなら、古い順に削除
        total_length = (
            len(system_message.content or "")
            + sum(len(m.content or "") for m in middle_messages)
            + sum(len(m.content or "") for m in recent_messages)
        )

        while total_length > CHAR_LIMIT and middle_messages:
            removed = middle_messages.pop(0)  # 古いものから削除
            total_length -= len(removed.content or "")

        # 再構築
        return [system_message, *middle_messages, *recent_messages]

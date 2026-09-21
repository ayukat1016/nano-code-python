"""共通の型定義。

TypeScript 版 (nano-code/src/types.ts) の型を Python に移植したもの。
Message は role によって意味を持つフィールドが変わる緩やかなレコードとして扱う
（TypeScript の判別可能なユニオン型の代わりに、単一の dataclass で表現する）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Optional, Protocol, AsyncIterator, runtime_checkable

Role = Literal["system", "user", "assistant", "tool"]
FinishReason = Literal["stop", "length", "content_filter", "tool_calls", "error"]


@dataclass
class ToolCall:
    """LLM が発行するツール呼び出し。"""

    tool_call_id: str
    name: str
    args: dict[str, Any]


@dataclass
class Message:
    """モデルとやりとりするメッセージ構造。

    role == "tool" のときは tool_call_id / name が必須、
    role == "assistant" のときのみ tool_calls を持ち得る。
    """

    role: Role
    content: str = ""
    tool_calls: Optional[list[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


@dataclass
class Usage:
    """使用量メタデータ（プロバイダ依存）。"""

    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


@dataclass
class ToolResult:
    """会話に追加されるツール実行結果。"""

    tool_call_id: str
    result: str


@dataclass
class Tool:
    """LLM が理解するツール定義（JSON スキーマ + 実行関数）。"""

    name: str
    description: str
    parameters: dict[str, Any]
    execute: Callable[[dict[str, Any]], Awaitable[str]]
    needs_approval: bool = False


@dataclass
class GenerateParams:
    """generate_text / generate_stream_text に渡すパラメータ。"""

    messages: list[Message]
    tools: Optional[list[Tool]] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@dataclass
class GenerateTextResult:
    """統一された LLM レスポンス。"""

    text: str
    finish_reason: FinishReason
    tool_calls: Optional[list[ToolCall]] = None
    usage: Optional[Usage] = None


@dataclass
class StreamChunk:
    """ストリーミングレスポンスの読み取り時に発行されるチャンク。"""

    kind: Literal["delta", "event", "done"]
    text: Optional[str] = None
    finish_reason: Optional[FinishReason] = None
    usage: Optional[Usage] = None
    tool_calls: Optional[list[ToolCall]] = None
    error: Optional[Any] = None


@runtime_checkable
class LanguageModel(Protocol):
    """各プロバイダが実装する言語モデルのインタフェース。

    do_stream はストリーミング対応モデルのみが実装するため必須ではない
    （呼び出し側は hasattr(model, "do_stream") で存在確認する）。
    """

    async def do_generate(self, params: GenerateParams) -> GenerateTextResult: ...

    def do_stream(self, params: GenerateParams) -> AsyncIterator[StreamChunk]: ...


# モデル ID に紐づいた言語モデルを返すプロバイダファクトリ
Provider = Callable[[str], LanguageModel]


class LLMApiError(Exception):
    """LLM API エラーの統一型。"""

    def __init__(
        self,
        status: int,
        provider: str,
        code: Optional[str] = None,
        message: Optional[str] = None,
        raw: Optional[Any] = None,
    ):
        super().__init__(message or f"LLM API Error: {provider} returned {status}")
        self.status = status
        self.provider = provider
        self.code = code
        self.raw = raw

"""ストリーミング応答の読み取りと結果の集約（付録A）。"""
from __future__ import annotations

from typing import AsyncIterator, Callable, Optional

from ..types import GenerateParams, GenerateTextResult, LanguageModel, Message, StreamChunk, Tool


async def generate_stream_text(
    model: LanguageModel,
    messages: list[Message],
    tools: Optional[list[Tool]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> AsyncIterator[StreamChunk]:
    if not hasattr(model, "do_stream"):
        raise RuntimeError("このモデルはストリーミングに対応していません")

    params = GenerateParams(
        messages=messages,
        tools=tools,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    async for chunk in model.do_stream(params):
        yield chunk


async def collect_stream_result(
    model: LanguageModel,
    messages: list[Message],
    tools: Optional[list[Tool]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    on_chunk: Optional[Callable[[StreamChunk], None]] = None,
) -> GenerateTextResult:
    text = ""
    finish_reason: str = "stop"
    usage = None
    tool_calls = None

    async for chunk in generate_stream_text(model, messages, tools, temperature, max_tokens):
        if on_chunk:
            on_chunk(chunk)

        if chunk.kind == "delta" and chunk.text:
            text += chunk.text

        if chunk.kind == "done":
            finish_reason = chunk.finish_reason or "stop"
            usage = chunk.usage
            tool_calls = chunk.tool_calls

    return GenerateTextResult(
        text=text,
        finish_reason=finish_reason,
        tool_calls=tool_calls,
        usage=usage,
    )

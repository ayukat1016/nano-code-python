"""Anthropic (Claude) プロバイダ実装。

`anthropic` パッケージ（AsyncAnthropic）に依存する。テスト容易性のため
client はコンストラクタ経由で差し替え可能にしてある。
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Optional

from ..types import (
    FinishReason,
    GenerateParams,
    GenerateTextResult,
    LLMApiError,
    Message,
    Provider,
    StreamChunk,
    ToolCall,
    Usage,
)
from ._helpers import get_attr
from .clean_messages import clean_messages


def _convert_messages(messages: list[Message]) -> list[dict[str, Any]]:
    # 履歴圧縮後も、ツール呼び出しと結果の対応が壊れないように補正する。
    cleaned = clean_messages(messages)
    converted: list[dict[str, Any]] = []

    for m in cleaned:
        if m.role == "system":
            continue

        # ツール結果は user ロール + tool_result ブロック
        if m.role == "tool":
            converted.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": m.tool_call_id,
                            "content": m.content,
                        }
                    ],
                }
            )
            continue

        # assistant のツール呼び出し
        if m.role == "assistant" and m.tool_calls:
            content: list[dict[str, Any]] = []
            if m.content:
                content.append({"type": "text", "text": m.content})
            for tc in m.tool_calls:
                content.append({"type": "tool_use", "id": tc.tool_call_id, "name": tc.name, "input": tc.args})
            converted.append({"role": "assistant", "content": content})
            continue

        converted.append({"role": m.role, "content": m.content})

    return converted


def _map_finish_reason(stop_reason: Optional[str]) -> FinishReason:
    return {
        "end_turn": "stop",
        "tool_use": "tool_calls",
        "max_tokens": "length",
    }.get(stop_reason or "", "stop")


def _wrap_error(error: Exception) -> Exception:
    try:
        import anthropic  # 遅延インポート（未インストール環境でも本モジュール自体は import 可能にする）
    except ImportError:
        return error

    if isinstance(error, anthropic.APIError):
        body = getattr(error, "body", None)
        code = None
        if isinstance(body, dict):
            code = body.get("error", {}).get("type")
        return LLMApiError(
            getattr(error, "status_code", 500),
            "anthropic",
            code,
            getattr(error, "message", str(error)),
            error,
        )
    return error


class _AnthropicModel:
    def __init__(self, client: Any, model_id: str):
        self._client = client
        self._model_id = model_id

    def _build_kwargs(self, params: GenerateParams, *, stream: bool) -> dict[str, Any]:
        system_messages = [m for m in params.messages if m.role == "system"]
        system = [{"type": "text", "text": m.content} for m in system_messages]

        tools = None
        if params.tools:
            tools = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in params.tools
            ]

        kwargs: dict[str, Any] = {
            "model": self._model_id,
            "system": system,
            "messages": _convert_messages(params.messages),
            "max_tokens": params.max_tokens or 4096,
        }
        if params.temperature is not None:
            kwargs["temperature"] = params.temperature
        if tools:
            kwargs["tools"] = tools
        if stream:
            kwargs["stream"] = True
        return kwargs

    async def do_generate(self, params: GenerateParams) -> GenerateTextResult:
        try:
            response = await self._client.messages.create(**self._build_kwargs(params, stream=False))
        except Exception as error:  # noqa: BLE001
            raise _wrap_error(error) from error

        content = get_attr(response, "content", [])
        text_blocks = [b for b in content if get_attr(b, "type") == "text"]
        text = "".join(get_attr(b, "text", "") for b in text_blocks)

        tool_use_blocks = [b for b in content if get_attr(b, "type") == "tool_use"]
        tool_calls = (
            [
                ToolCall(
                    tool_call_id=get_attr(b, "id"),
                    name=get_attr(b, "name"),
                    args=get_attr(b, "input") or {},
                )
                for b in tool_use_blocks
            ]
            if tool_use_blocks
            else None
        )

        usage = get_attr(response, "usage")
        input_tokens = get_attr(usage, "input_tokens", 0) or 0
        output_tokens = get_attr(usage, "output_tokens", 0) or 0

        return GenerateTextResult(
            text=text,
            finish_reason=_map_finish_reason(get_attr(response, "stop_reason")),
            tool_calls=tool_calls,
            usage=Usage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
        )

    async def do_stream(self, params: GenerateParams) -> AsyncIterator[StreamChunk]:
        try:
            stream = await self._client.messages.create(**self._build_kwargs(params, stream=True))
        except Exception as error:  # noqa: BLE001
            raise _wrap_error(error) from error

        tool_calls: dict[str, ToolCall] = {}
        partial_json_buffers: dict[str, str] = {}
        index_to_id: dict[int, str] = {}
        finish_reason: Optional[FinishReason] = None
        usage: Optional[Usage] = None

        try:
            async for event in stream:
                event_type = get_attr(event, "type")

                if event_type == "content_block_start":
                    block = get_attr(event, "content_block")
                    if block is not None and get_attr(block, "type") == "tool_use":
                        block_id = get_attr(block, "id")
                        index_to_id[get_attr(event, "index")] = block_id
                        tool_calls[block_id] = ToolCall(
                            tool_call_id=block_id, name=get_attr(block, "name"), args={}
                        )
                        partial_json_buffers[block_id] = ""

                elif event_type == "content_block_delta":
                    delta = get_attr(event, "delta")
                    delta_type = get_attr(delta, "type")
                    if delta_type == "text_delta":
                        yield StreamChunk(kind="delta", text=get_attr(delta, "text"))
                    if delta_type == "input_json_delta":
                        block_id = index_to_id.get(get_attr(event, "index"))
                        tool_call = tool_calls.get(block_id) if block_id else None
                        if block_id and tool_call:
                            buffer = partial_json_buffers.get(block_id, "") + get_attr(delta, "partial_json", "")
                            partial_json_buffers[block_id] = buffer
                            try:
                                import json

                                tool_call.args = json.loads(buffer)
                            except ValueError:
                                pass  # JSON が不完全な場合は次のデルタを待つ

                elif event_type == "message_delta":
                    delta = get_attr(event, "delta")
                    stop_reason = get_attr(delta, "stop_reason")
                    if stop_reason:
                        finish_reason = _map_finish_reason(stop_reason)
                    event_usage = get_attr(event, "usage")
                    if event_usage is not None:
                        input_tokens = get_attr(event_usage, "input_tokens") or 0
                        output_tokens = get_attr(event_usage, "output_tokens") or 0
                        usage = Usage(
                            prompt_tokens=input_tokens,
                            completion_tokens=output_tokens,
                            total_tokens=input_tokens + output_tokens,
                        )

                elif event_type == "message_stop":
                    tool_call_list = list(tool_calls.values())
                    yield StreamChunk(
                        kind="done",
                        finish_reason=finish_reason,
                        usage=usage,
                        tool_calls=tool_call_list if tool_call_list else None,
                    )
                    return
        except Exception as error:  # noqa: BLE001
            raise _wrap_error(error) from error


def create_anthropic(
    api_key: Optional[str] = None,
    max_retries: int = 0,
    client: Optional[Any] = None,
) -> Provider:
    if client is None:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=max_retries)

    def provider(model_id: str):
        return _AnthropicModel(client, model_id)

    return provider

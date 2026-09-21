"""OpenAI (Chat Completions API) プロバイダ実装。"""
from __future__ import annotations

import json
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

_FINISH_REASON_MAP: dict[str, FinishReason] = {
    "stop": "stop",
    "length": "length",
    "content_filter": "content_filter",
    "tool_calls": "tool_calls",
}


def _convert_messages(messages: list[Message]) -> list[dict[str, Any]]:
    # 履歴圧縮後も、ツール呼び出しと結果の対応が壊れないように補正する。
    cleaned = clean_messages(messages)
    converted: list[dict[str, Any]] = []

    for m in cleaned:
        if m.role == "tool":
            converted.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
            continue
        if m.role == "assistant" and m.tool_calls:
            converted.append(
                {
                    "role": "assistant",
                    "content": m.content,
                    "tool_calls": [
                        {
                            "id": tc.tool_call_id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.args, ensure_ascii=False)},
                        }
                        for tc in m.tool_calls
                    ],
                }
            )
            continue
        converted.append({"role": m.role, "content": m.content})

    return converted


def _map_finish_reason(reason: Optional[str]) -> FinishReason:
    return _FINISH_REASON_MAP.get(reason or "", "stop")


def _parse_tool_call_args(args_text: Optional[str]) -> dict[str, Any]:
    if not args_text:
        return {}
    try:
        return json.loads(args_text)
    except ValueError:
        # 不正な JSON では例外を伝播させない。
        return {}


def _wrap_error(error: Exception) -> Exception:
    try:
        import openai
    except ImportError:
        return error

    if isinstance(error, openai.APIError):
        return LLMApiError(
            getattr(error, "status_code", 500),
            "openai",
            getattr(error, "code", None),
            getattr(error, "message", str(error)),
            error,
        )
    return error


class _OpenAIModel:
    def __init__(self, client: Any, model_id: str):
        self._client = client
        self._model_id = model_id

    def _build_tools(self, params: GenerateParams) -> Optional[list[dict[str, Any]]]:
        if not params.tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in params.tools
        ]

    async def do_generate(self, params: GenerateParams) -> GenerateTextResult:
        tools = self._build_tools(params)

        kwargs: dict[str, Any] = {
            "model": self._model_id,
            "messages": _convert_messages(params.messages),
            "temperature": params.temperature,
        }
        if params.max_tokens is not None:
            kwargs["max_completion_tokens"] = params.max_tokens
        if tools:
            kwargs["tools"] = tools

        try:
            completion = await self._client.chat.completions.create(**kwargs)
        except Exception as error:  # noqa: BLE001
            raise _wrap_error(error) from error

        choices = get_attr(completion, "choices", [])
        if not choices:
            raise LLMApiError(500, "openai", None, "APIからの応答がありません")

        choice = choices[0]
        message = get_attr(choice, "message")

        raw_tool_calls = get_attr(message, "tool_calls")
        tool_calls = (
            [
                ToolCall(
                    tool_call_id=get_attr(tc, "id"),
                    name=get_attr(get_attr(tc, "function"), "name"),
                    args=_parse_tool_call_args(get_attr(get_attr(tc, "function"), "arguments")),
                )
                for tc in raw_tool_calls
            ]
            if raw_tool_calls
            else None
        )

        usage = get_attr(completion, "usage")
        return GenerateTextResult(
            text=get_attr(message, "content") or "",
            finish_reason=_map_finish_reason(get_attr(choice, "finish_reason")),
            tool_calls=tool_calls,
            usage=(
                Usage(
                    prompt_tokens=get_attr(usage, "prompt_tokens"),
                    completion_tokens=get_attr(usage, "completion_tokens"),
                    total_tokens=get_attr(usage, "total_tokens"),
                )
                if usage is not None
                else None
            ),
        )

    async def do_stream(self, params: GenerateParams) -> AsyncIterator[StreamChunk]:
        tools = self._build_tools(params)

        kwargs: dict[str, Any] = {
            "model": self._model_id,
            "messages": _convert_messages(params.messages),
            "temperature": params.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if params.max_tokens is not None:
            kwargs["max_completion_tokens"] = params.max_tokens
        if tools:
            kwargs["tools"] = tools

        try:
            stream = await self._client.chat.completions.create(**kwargs)
        except Exception as error:  # noqa: BLE001
            raise _wrap_error(error) from error

        tool_call_buffer: dict[str, dict[str, str]] = {}
        auto_index = 0
        finish_reason: Optional[FinishReason] = None
        usage: Optional[Usage] = None

        try:
            async for chunk in stream:
                choices = get_attr(chunk, "choices") or []
                choice = choices[0] if choices else None
                delta = get_attr(choice, "delta") if choice is not None else None

                if delta is not None and get_attr(delta, "content"):
                    yield StreamChunk(kind="delta", text=get_attr(delta, "content"))

                delta_tool_calls = get_attr(delta, "tool_calls") if delta is not None else None
                if delta_tool_calls:
                    for tc in delta_tool_calls:
                        tc_id = get_attr(tc, "id")
                        tc_index = get_attr(tc, "index")
                        key = tc_id or str(tc_index if tc_index is not None else auto_index)
                        if key not in tool_call_buffer:
                            auto_index += 1
                        existing = tool_call_buffer.setdefault(key, {"id": tc_id or key, "name": "", "args_text": ""})

                        function = get_attr(tc, "function")
                        name = get_attr(function, "name")
                        arguments = get_attr(function, "arguments")
                        if name:
                            existing["name"] = name
                        if arguments:
                            existing["args_text"] += arguments

                if choice is not None and get_attr(choice, "finish_reason"):
                    finish_reason = _map_finish_reason(get_attr(choice, "finish_reason"))

                chunk_usage = get_attr(chunk, "usage")
                if chunk_usage is not None:
                    usage = Usage(
                        prompt_tokens=get_attr(chunk_usage, "prompt_tokens"),
                        completion_tokens=get_attr(chunk_usage, "completion_tokens"),
                        total_tokens=get_attr(chunk_usage, "total_tokens"),
                    )
        except Exception as error:  # noqa: BLE001
            raise _wrap_error(error) from error

        tool_calls = [
            ToolCall(tool_call_id=tc["id"], name=tc["name"], args=_parse_tool_call_args(tc["args_text"]))
            for tc in tool_call_buffer.values()
        ]

        yield StreamChunk(
            kind="done",
            finish_reason=finish_reason,
            usage=usage,
            tool_calls=tool_calls if tool_calls else None,
        )


def create_openai(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    max_retries: int = 0,
    client: Optional[Any] = None,
) -> Provider:
    if client is None:
        import openai

        client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=max_retries)

    def provider(model_id: str):
        return _OpenAIModel(client, model_id)

    return provider

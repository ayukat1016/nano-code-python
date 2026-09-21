"""Google Gemini (google-genai SDK) プロバイダ実装。"""
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

        # ツール結果は user ロール + functionResponse
        if m.role == "tool":
            converted.append(
                {
                    "role": "user",
                    "parts": [{"function_response": {"name": m.name, "response": {"result": m.content}}}],
                }
            )
            continue

        # assistant のツール呼び出し
        if m.role == "assistant" and m.tool_calls:
            parts: list[dict[str, Any]] = []
            if m.content:
                parts.append({"text": m.content})
            for tc in m.tool_calls:
                parts.append({"function_call": {"name": tc.name, "args": tc.args}})
            converted.append({"role": "model", "parts": parts})
            continue

        # 通常のメッセージ
        role = "model" if m.role == "assistant" else "user"
        converted.append({"role": role, "parts": [{"text": m.content}]})

    return converted


def _map_finish_reason(reason: Optional[str], has_function_call: bool) -> FinishReason:
    if has_function_call:
        return "tool_calls"
    return {
        "STOP": "stop",
        "MAX_TOKENS": "length",
        "SAFETY": "content_filter",
    }.get((reason or "").upper(), "stop")


def _finish_reason_str(candidate: Any) -> Optional[str]:
    reason = get_attr(candidate, "finish_reason")
    return getattr(reason, "value", reason)


def _build_tools(params: GenerateParams) -> Optional[list[dict[str, Any]]]:
    if not params.tools:
        return None
    return [
        {
            "function_declarations": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    # google-genai の Schema (OBJECT/STRING...) 型付けを避け、
                    # 標準 JSON Schema をそのまま渡せる parameters_json_schema を使う。
                    "parameters_json_schema": tool.parameters,
                }
                for tool in params.tools
            ]
        }
    ]


def _wrap_error(error: Exception) -> Exception:
    try:
        from google.genai import errors
    except ImportError:
        return error

    if isinstance(error, errors.APIError):
        return LLMApiError(
            getattr(error, "code", 500) or 500,
            "google",
            getattr(error, "status", None),
            getattr(error, "message", str(error)),
            error,
        )
    return error


class _GoogleModel:
    def __init__(self, client: Any, model_id: str):
        self._client = client
        self._model_id = model_id

    def _build_config(self, params: GenerateParams) -> dict[str, Any]:
        system_messages = [m for m in params.messages if m.role == "system"]
        system_instruction = "\n".join(m.content for m in system_messages)

        config: dict[str, Any] = {
            "system_instruction": system_instruction,
            "temperature": params.temperature,
            "max_output_tokens": params.max_tokens,
        }
        tools = _build_tools(params)
        if tools:
            config["tools"] = tools
        return config

    async def do_generate(self, params: GenerateParams) -> GenerateTextResult:
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model_id,
                contents=_convert_messages(params.messages),
                config=self._build_config(params),
            )
        except Exception as error:  # noqa: BLE001
            raise _wrap_error(error) from error

        candidates = get_attr(response, "candidates") or []
        candidate = candidates[0] if candidates else None
        content = get_attr(candidate, "content")
        parts = get_attr(content, "parts") or []

        text_parts = [p for p in parts if get_attr(p, "text")]
        text = "".join(get_attr(p, "text", "") for p in text_parts)

        function_call_parts = [p for p in parts if get_attr(p, "function_call")]
        tool_calls = (
            [
                ToolCall(
                    tool_call_id=get_attr(get_attr(p, "function_call"), "id") or f"call_{i}",
                    name=get_attr(get_attr(p, "function_call"), "name"),
                    args=get_attr(get_attr(p, "function_call"), "args") or {},
                )
                for i, p in enumerate(function_call_parts)
            ]
            if function_call_parts
            else None
        )

        usage = get_attr(response, "usage_metadata")

        return GenerateTextResult(
            text=text,
            finish_reason=_map_finish_reason(_finish_reason_str(candidate), bool(function_call_parts)),
            tool_calls=tool_calls,
            usage=Usage(
                prompt_tokens=get_attr(usage, "prompt_token_count"),
                completion_tokens=get_attr(usage, "candidates_token_count"),
                total_tokens=get_attr(usage, "total_token_count"),
            ),
        )

    async def do_stream(self, params: GenerateParams) -> AsyncIterator[StreamChunk]:
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self._model_id,
                contents=_convert_messages(params.messages),
                config=self._build_config(params),
            )
        except Exception as error:  # noqa: BLE001
            raise _wrap_error(error) from error

        tool_calls: dict[str, ToolCall] = {}
        tool_call_index = 0
        finish_reason: Optional[FinishReason] = None
        usage: Optional[Usage] = None

        try:
            async for chunk in stream:
                candidates = get_attr(chunk, "candidates") or []
                candidate = candidates[0] if candidates else None
                parts = get_attr(get_attr(candidate, "content"), "parts") or []

                for part in parts:
                    text = get_attr(part, "text")
                    if text:
                        yield StreamChunk(kind="delta", text=text)

                    function_call = get_attr(part, "function_call")
                    if function_call:
                        # 同一関数を複数回呼び出しても上書きしないよう、連番の ID を使う。
                        call_id = f"call_{tool_call_index}"
                        tool_call_index += 1
                        tool_calls[call_id] = ToolCall(
                            tool_call_id=call_id,
                            name=get_attr(function_call, "name"),
                            args=get_attr(function_call, "args") or {},
                        )

                if candidate is not None and get_attr(candidate, "finish_reason"):
                    finish_reason = _map_finish_reason(_finish_reason_str(candidate), bool(tool_calls))

                chunk_usage = get_attr(chunk, "usage_metadata")
                if chunk_usage is not None:
                    prompt_tokens = get_attr(chunk_usage, "prompt_token_count") or 0
                    completion_tokens = get_attr(chunk_usage, "candidates_token_count") or 0
                    usage = Usage(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=prompt_tokens + completion_tokens,
                    )
        except Exception as error:  # noqa: BLE001
            raise _wrap_error(error) from error

        tool_call_list = list(tool_calls.values())
        yield StreamChunk(
            kind="done",
            finish_reason=finish_reason,
            usage=usage,
            tool_calls=tool_call_list if tool_call_list else None,
        )


def create_google(api_key: Optional[str] = None, client: Optional[Any] = None) -> Provider:
    if client is None:
        from google import genai

        client = genai.Client(api_key=api_key)

    def provider(model_id: str):
        return _GoogleModel(client, model_id)

    return provider

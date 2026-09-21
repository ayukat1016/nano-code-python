from types import SimpleNamespace

import pytest

from src.providers.google_provider import create_google
from src.types import GenerateParams, Message


class _FakeModels:
    def __init__(self, response):
        self._response = response
        self.calls = []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeAio:
    def __init__(self, response):
        self.models = _FakeModels(response)


class _FakeClient:
    def __init__(self, response):
        self.aio = _FakeAio(response)


@pytest.mark.asyncio
async def test_do_generate_with_text_response():
    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(parts=[SimpleNamespace(text="こんにちは", function_call=None)]),
                finish_reason="STOP",
            )
        ],
        usage_metadata=SimpleNamespace(prompt_token_count=14, candidates_token_count=7, total_token_count=21),
    )
    client = _FakeClient(response)

    provider = create_google(client=client)
    model = provider("gemini-2.5-flash")

    result = await model.do_generate(GenerateParams(messages=[Message(role="user", content="こんにちは")]))

    assert result.text == "こんにちは"
    assert result.finish_reason == "stop"
    assert result.usage.prompt_tokens == 14
    assert result.usage.completion_tokens == 7
    assert result.usage.total_tokens == 21

    called_kwargs = client.aio.models.calls[0]
    assert called_kwargs["model"] == "gemini-2.5-flash"
    assert called_kwargs["contents"] == [{"role": "user", "parts": [{"text": "こんにちは"}]}]


@pytest.mark.asyncio
async def test_do_generate_with_tool_calls():
    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(
                            text=None,
                            function_call=SimpleNamespace(name="readFile", args={"path": "test.txt"}, id=None),
                        )
                    ]
                ),
                # Geminiはツール呼び出し時も通常STOPを返す（hasFunctionCallフラグで判定）
                finish_reason="STOP",
            )
        ],
        usage_metadata=SimpleNamespace(prompt_token_count=20, candidates_token_count=15, total_token_count=35),
    )
    client = _FakeClient(response)

    provider = create_google(client=client)
    model = provider("gemini-2.5-flash")

    result = await model.do_generate(GenerateParams(messages=[Message(role="user", content="ファイル読んで")]))

    assert result.text == ""
    assert result.finish_reason == "tool_calls"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "readFile"
    assert result.tool_calls[0].args == {"path": "test.txt"}

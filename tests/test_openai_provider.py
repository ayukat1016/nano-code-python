from types import SimpleNamespace

import pytest

from src.providers.openai_provider import create_openai
from src.types import GenerateParams, Message


class _FakeCompletions:
    def __init__(self, response):
        self._response = response
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeChat:
    def __init__(self, response):
        self.completions = _FakeCompletions(response)


class _FakeClient:
    def __init__(self, response):
        self.chat = _FakeChat(response)


@pytest.mark.asyncio
async def test_do_generate_with_text_response():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(role="assistant", content="こんにちは", tool_calls=None),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )
    client = _FakeClient(response)

    provider = create_openai(client=client)
    model = provider("gpt-5-mini")

    result = await model.do_generate(GenerateParams(messages=[Message(role="user", content="こんにちは")]))

    assert result.text == "こんにちは"
    assert result.finish_reason == "stop"
    assert result.usage.prompt_tokens == 10
    assert result.usage.completion_tokens == 5
    assert result.usage.total_tokens == 15

    called_kwargs = client.chat.completions.calls[0]
    assert called_kwargs["model"] == "gpt-5-mini"
    assert called_kwargs["messages"] == [{"role": "user", "content": "こんにちは"}]


@pytest.mark.asyncio
async def test_do_generate_with_tool_calls():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call_123",
                            type="function",
                            function=SimpleNamespace(name="readFile", arguments='{"path":"test.txt"}'),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ],
        usage=None,
    )
    client = _FakeClient(response)

    provider = create_openai(client=client)
    model = provider("gpt-5-mini")

    result = await model.do_generate(GenerateParams(messages=[Message(role="user", content="ファイル読んで")]))

    assert result.text == ""
    assert result.finish_reason == "tool_calls"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_call_id == "call_123"
    assert result.tool_calls[0].name == "readFile"
    assert result.tool_calls[0].args == {"path": "test.txt"}

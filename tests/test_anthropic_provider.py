from types import SimpleNamespace

import pytest

from src.providers.anthropic_provider import create_anthropic
from src.types import Message


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


@pytest.mark.asyncio
async def test_do_generate_with_text_response():
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="こんにちは")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=12, output_tokens=6),
    )
    client = _FakeClient(response)

    provider = create_anthropic(client=client)
    model = provider("claude-haiku-4-5-20251001")

    from src.types import GenerateParams

    result = await model.do_generate(GenerateParams(messages=[Message(role="user", content="こんにちは")]))

    assert result.text == "こんにちは"
    assert result.finish_reason == "stop"
    assert result.usage.prompt_tokens == 12
    assert result.usage.completion_tokens == 6
    assert result.usage.total_tokens == 18

    called_kwargs = client.messages.calls[0]
    assert called_kwargs["model"] == "claude-haiku-4-5-20251001"
    assert called_kwargs["messages"] == [{"role": "user", "content": "こんにちは"}]


@pytest.mark.asyncio
async def test_do_generate_with_tool_calls():
    response = SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", id="toolu_123", name="readFile", input={"path": "test.txt"})],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=15, output_tokens=10),
    )
    client = _FakeClient(response)

    provider = create_anthropic(client=client)
    model = provider("claude-haiku-4-5-20251001")

    from src.types import GenerateParams

    result = await model.do_generate(GenerateParams(messages=[Message(role="user", content="ファイル読んで")]))

    assert result.text == ""
    assert result.finish_reason == "tool_calls"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_call_id == "toolu_123"
    assert result.tool_calls[0].name == "readFile"
    assert result.tool_calls[0].args == {"path": "test.txt"}

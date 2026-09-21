import pytest

from src.core.generate_text import generate_text
from src.types import GenerateParams, GenerateTextResult, Message


@pytest.mark.asyncio
async def test_generate_text_passes_params_through_to_do_generate():
    received: GenerateParams | None = None

    class _Model:
        async def do_generate(self, params: GenerateParams) -> GenerateTextResult:
            nonlocal received
            received = params
            return GenerateTextResult(text="ok", finish_reason="stop")

    messages = [Message(role="user", content="hello")]
    result = await generate_text(_Model(), messages, temperature=0.25, max_tokens=123)

    assert result.text == "ok"
    assert received is not None
    assert received.messages == messages
    assert received.temperature == 0.25
    assert received.max_tokens == 123
    assert received.tools is None

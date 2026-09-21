import pytest

from src.core.generate_stream import collect_stream_result, generate_stream_text
from src.types import GenerateTextResult, Message, StreamChunk, ToolCall


@pytest.mark.asyncio
async def test_generate_stream_text_raises_when_unsupported():
    class _Model:
        async def do_generate(self, params):
            return GenerateTextResult(text="ok", finish_reason="stop")

    with pytest.raises(RuntimeError, match="このモデルはストリーミングに対応していません"):
        async for _ in generate_stream_text(_Model(), [Message(role="user", content="hello")]):
            pass


@pytest.mark.asyncio
async def test_collect_stream_result_accumulates_deltas_and_returns_done_payload():
    tool_calls = [ToolCall(tool_call_id="call_0", name="readFile", args={"path": "hello.txt"})]

    chunks = [
        StreamChunk(kind="event"),
        StreamChunk(kind="delta", text="Hel"),
        StreamChunk(kind="delta", text="lo"),
        StreamChunk(
            kind="done",
            finish_reason="tool_calls",
            usage=None,
            tool_calls=tool_calls,
        ),
    ]

    class _Model:
        async def do_generate(self, params):
            return GenerateTextResult(text="ok", finish_reason="stop")

        async def do_stream(self, params):
            for chunk in chunks:
                yield chunk

    seen_kinds: list[str] = []
    result = await collect_stream_result(
        _Model(),
        [Message(role="user", content="hello")],
        on_chunk=lambda chunk: seen_kinds.append(chunk.kind),
    )

    assert seen_kinds == ["event", "delta", "delta", "done"]
    assert result.text == "Hello"
    assert result.finish_reason == "tool_calls"
    assert result.tool_calls == tool_calls

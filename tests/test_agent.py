import pytest

from src.core.agent import Agent, AgentConfig
from src.types import GenerateParams, GenerateTextResult, Message, Tool, ToolCall


class _FakeModel:
    def __init__(self, do_generate):
        self._do_generate = do_generate

    async def do_generate(self, params: GenerateParams) -> GenerateTextResult:
        return await self._do_generate(params)


@pytest.mark.asyncio
async def test_agent_runs_tool_then_finishes():
    call_history: list[list[Message]] = []
    step = 0

    async def do_generate(params: GenerateParams) -> GenerateTextResult:
        nonlocal step
        call_history.append(list(params.messages))
        step += 1
        if step == 1:
            return GenerateTextResult(
                text="検索ツールを使います。",
                finish_reason="stop",
                tool_calls=[ToolCall(tool_call_id="call_1", name="search", args={"query": "test"})],
            )
        return GenerateTextResult(text="検索結果を確認しました。タスク完了です。", finish_reason="stop")

    async def search_execute(args):
        return f"「{args['query']}」の検索結果: 成功"

    search_tool = Tool(
        name="search",
        description="テスト用の検索ツール",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        execute=search_execute,
    )

    agent = Agent(
        AgentConfig(
            name="test-agent",
            instructions="指示内容",
            model=_FakeModel(do_generate),
            tools={"search": search_tool},
            max_steps=5,
        )
    )

    result = await agent.generate("テスト検索を行ってください")

    assert result["text"] == "検索結果を確認しました。タスク完了です。"
    assert step == 2
    assert len(call_history) == 2

    last_message = call_history[1][-1]
    assert last_message.role == "tool"
    assert last_message.name == "search"
    assert last_message.content == "「test」の検索結果: 成功"


@pytest.mark.asyncio
async def test_agent_stops_at_max_steps():
    step = 0

    async def do_generate(params: GenerateParams) -> GenerateTextResult:
        nonlocal step
        step += 1
        return GenerateTextResult(
            text=f"思考ステップ {step}",
            finish_reason="stop",
            tool_calls=[ToolCall(tool_call_id=f"call_{step}", name="dummy", args={})],
        )

    dummy_tool = Tool(name="dummy", description="ダミーツール", parameters={}, execute=lambda args: _ok())

    async def _ok():
        return "完了"

    agent = Agent(
        AgentConfig(
            name="limit-agent",
            instructions="指示内容",
            model=_FakeModel(do_generate),
            tools={"dummy": dummy_tool},
            max_steps=3,
        )
    )

    await agent.generate("終わらないタスク")
    assert step == 3


@pytest.mark.asyncio
async def test_agent_executes_tool_when_approved():
    executed = False

    async def do_generate(params: GenerateParams) -> GenerateTextResult:
        return GenerateTextResult(
            text="書き込みます。",
            finish_reason="stop",
            tool_calls=[ToolCall(tool_call_id="call_1", name="write", args={"content": "hello"})],
        )

    async def write_execute(args):
        nonlocal executed
        executed = True
        return "書き込み成功"

    write_tool = Tool(name="write", description="テスト用の書き込みツール", needs_approval=True, parameters={}, execute=write_execute)

    async def approval_func(name, args):
        return True

    agent = Agent(
        AgentConfig(
            name="approval-agent",
            instructions="指示内容",
            model=_FakeModel(do_generate),
            tools={"write": write_tool},
            approval_func=approval_func,
            max_steps=2,
        )
    )

    await agent.generate("書き込んで")
    assert executed is True


@pytest.mark.asyncio
async def test_agent_skips_tool_when_rejected():
    executed = False
    call_history: list[list[Message]] = []

    async def do_generate(params: GenerateParams) -> GenerateTextResult:
        call_history.append(list(params.messages))
        if len(call_history) == 1:
            return GenerateTextResult(
                text="書き込みます。",
                finish_reason="stop",
                tool_calls=[ToolCall(tool_call_id="call_1", name="write", args={"content": "hello"})],
            )
        return GenerateTextResult(text="拒否されたので諦めます。", finish_reason="stop")

    async def write_execute(args):
        nonlocal executed
        executed = True
        return "書き込み成功"

    write_tool = Tool(name="write", description="テスト用の書き込みツール", needs_approval=True, parameters={}, execute=write_execute)

    async def approval_func(name, args):
        return False

    agent = Agent(
        AgentConfig(
            name="reject-agent",
            instructions="指示内容",
            model=_FakeModel(do_generate),
            tools={"write": write_tool},
            approval_func=approval_func,
            max_steps=2,
        )
    )

    await agent.generate("書き込んで")
    assert executed is False
    assert len(call_history) == 2

    last_message = call_history[1][-1]
    assert last_message.role == "tool"
    assert last_message.name == "write"
    assert last_message.content == "ユーザーによってキャンセルされました。別の方法を検討してください。"


@pytest.mark.asyncio
async def test_agent_uses_streaming_when_supported():
    stream_called = False

    class _StreamingModel:
        async def do_generate(self, params):
            raise AssertionError("Streaming should be used instead of do_generate")

        async def do_stream(self, params):
            nonlocal stream_called
            stream_called = True
            from src.types import StreamChunk

            yield StreamChunk(kind="delta", text="スト")
            yield StreamChunk(kind="delta", text="リーム")
            yield StreamChunk(kind="done", finish_reason="stop")

    agent = Agent(
        AgentConfig(
            name="stream-agent",
            instructions="指示内容",
            model=_StreamingModel(),
            tools={},
            use_streaming=True,
            max_steps=2,
        )
    )

    result = await agent.generate("ストリームで返して")
    assert stream_called is True
    assert result["text"] == "ストリーム"


@pytest.mark.asyncio
async def test_agent_manages_context_when_exceeding_char_limit():
    last_received_messages: list[Message] = []
    step = 0

    async def do_generate(params: GenerateParams) -> GenerateTextResult:
        nonlocal last_received_messages, step
        last_received_messages = params.messages
        step += 1
        if step < 5:
            return GenerateTextResult(
                text="ツールを使います。",
                finish_reason="stop",
                tool_calls=[ToolCall(tool_call_id=f"call_{step}", name="dummy", args={})],
            )
        return GenerateTextResult(text="完了しました。", finish_reason="stop")

    async def dummy_execute(args):
        return "結果" * 6000  # 12000文字

    dummy_tool = Tool(name="dummy", description="ダミーツール", parameters={}, execute=dummy_execute)

    agent = Agent(
        AgentConfig(
            name="context-agent",
            instructions="システム指示",
            model=_FakeModel(do_generate),
            tools={"dummy": dummy_tool},
            max_steps=10,
        )
    )

    await agent.generate("開始します")

    total_length = sum(len(m.content or "") for m in last_received_messages)
    assert total_length <= 30000

    assert any("以前のツール実行結果は省略されました" in (m.content or "") for m in last_received_messages)

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))

from review import clean_messages  # noqa: E402
from src.types import Message, ToolCall  # noqa: E402


def test_passes_through_fully_consistent_messages():
    messages = [
        Message(role="user", content="hello"),
        Message(
            role="assistant",
            content="let me run a tool",
            tool_calls=[ToolCall(tool_call_id="1", name="dummy", args={})],
        ),
        Message(role="tool", tool_call_id="1", name="dummy", content="result"),
        Message(role="assistant", content="done"),
    ]

    assert clean_messages(messages) == messages


def test_recovers_unmatched_tool_response_with_dummy_assistant_message():
    messages = [
        Message(role="user", content="hello"),
        # 親である assistant (toolCalls: '1') が manageContext 等で消えた想定
        Message(role="tool", tool_call_id="1", name="dummy", content="result"),
        Message(role="assistant", content="done"),
    ]

    cleaned = clean_messages(messages)

    assert cleaned == [
        Message(role="user", content="hello"),
        Message(
            role="assistant",
            content="ツールを実行します。",
            tool_calls=[ToolCall(tool_call_id="1", name="dummy", args={})],
        ),
        Message(role="tool", tool_call_id="1", name="dummy", content="result"),
        Message(role="assistant", content="done"),
    ]


def test_falls_back_to_dummy_user_message_if_only_system_remains():
    messages = [Message(role="system", content="you are a reviewer")]

    cleaned = clean_messages(messages)

    assert cleaned == [
        Message(role="system", content="you are a reviewer"),
        Message(role="user", content="続けてください。"),
    ]


def test_strips_unmatched_tool_calls_from_assistant_message():
    messages = [
        Message(role="user", content="hello"),
        Message(
            role="assistant",
            content="let me run a tool",
            tool_calls=[ToolCall(tool_call_id="1", name="dummy", args={})],
        ),
        # 子である tool (toolCallId: '1') が manageContext 等で消えた想定
        Message(role="assistant", content="done"),
    ]

    cleaned = clean_messages(messages)

    assert cleaned == [
        Message(role="user", content="hello"),
        Message(role="assistant", content="let me run a tool"),
        Message(role="assistant", content="done"),
    ]


def test_keeps_only_matched_tool_calls_among_multiple():
    messages = [
        Message(
            role="assistant",
            content="running tools",
            tool_calls=[
                ToolCall(tool_call_id="1", name="dummy1", args={}),
                ToolCall(tool_call_id="2", name="dummy2", args={}),
            ],
        ),
        Message(role="tool", tool_call_id="1", name="dummy1", content="res1"),
        # 'dummy2' の tool レスポンスが消えた想定
    ]

    cleaned = clean_messages(messages)

    assert cleaned == [
        Message(
            role="assistant",
            content="running tools",
            tool_calls=[ToolCall(tool_call_id="1", name="dummy1", args={})],
        ),
        Message(role="tool", tool_call_id="1", name="dummy1", content="res1"),
    ]

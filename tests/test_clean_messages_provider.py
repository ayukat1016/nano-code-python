from src.providers.clean_messages import clean_messages
from src.types import Message, ToolCall


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


def test_drops_orphan_tool_message_when_parent_assistant_missing():
    messages = [
        Message(role="user", content="hello"),
        # 親である assistant (toolCalls: '1') が manageContext 等で消えた想定
        Message(role="tool", tool_call_id="1", name="dummy", content="result"),
        Message(role="assistant", content="done"),
    ]

    cleaned = clean_messages(messages)

    assert cleaned == [
        Message(role="user", content="hello"),
        Message(role="assistant", content="done"),
    ]


def test_falls_back_to_dummy_user_message_if_only_system_remains():
    messages = [Message(role="system", content="you are an agent")]

    cleaned = clean_messages(messages)

    assert cleaned == [
        Message(role="system", content="you are an agent"),
        Message(role="user", content="続けてください。"),
    ]


def test_strips_unmatched_tool_calls_from_assistant_message():
    messages = [
        Message(
            role="assistant",
            content="let me run a tool",
            tool_calls=[ToolCall(tool_call_id="1", name="dummy", args={})],
        ),
        Message(role="assistant", content="done"),
    ]

    cleaned = clean_messages(messages)

    assert cleaned == [
        Message(role="assistant", content="let me run a tool"),
        Message(role="assistant", content="done"),
    ]

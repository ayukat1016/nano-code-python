"""LangGraphで組んだ思考ループ本体。

src/core/agent.py（約150行の自前ループ実装）に相当する部分が、
StateGraphのノード定義と条件分岐エッジだけで表現できる。
承認ゲート（src/core/approval.py）は langgraph.types.interrupt に置き換わる。
"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import tools_condition
from langgraph.types import interrupt

from tools import ALL_TOOLS, TOOLS_NEEDING_APPROVAL

TOOLS_BY_NAME = {t.name: t for t in ALL_TOOLS}


def build_graph(model: BaseChatModel):
    model_with_tools = model.bind_tools(ALL_TOOLS)

    def call_model(state: MessagesState) -> dict:
        response = model_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    def run_tools(state: MessagesState) -> dict:
        last_message = state["messages"][-1]
        results: list[ToolMessage] = []

        for tool_call in last_message.tool_calls:
            name = tool_call["name"]
            args = tool_call["args"]
            tool_call_id = tool_call["id"]

            # 承認ゲート: needs_approval 相当のツールは interrupt() でグラフの実行を一時停止する。
            # 人間が Command(resume=True/False) で再開すると、ここから処理が続く。
            if name in TOOLS_NEEDING_APPROVAL:
                approved = interrupt({"tool": name, "args": args})
                if not approved:
                    results.append(
                        ToolMessage(
                            content="ユーザーによってキャンセルされました。別の方法を検討してください。",
                            tool_call_id=tool_call_id,
                        )
                    )
                    continue

            tool_fn = TOOLS_BY_NAME.get(name)
            if tool_fn is None:
                results.append(ToolMessage(content=f"エラー: ツール {name} が見つかりません", tool_call_id=tool_call_id))
                continue

            try:
                output = tool_fn.invoke(args)
            except Exception as error:  # ツールの例外はエラーメッセージとして会話に戻す
                output = f"エラー: {error}"

            results.append(ToolMessage(content=str(output), tool_call_id=tool_call_id))

        return {"messages": results}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", run_tools)
    graph.add_edge(START, "agent")
    # tools_condition: 直近のAIMessageにtool_callsがあれば"tools"へ、無ければ終了。
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    # interrupt()での一時停止・再開にはcheckpointerが必須（会話状態を保持するため）。
    return graph.compile(checkpointer=MemorySaver())

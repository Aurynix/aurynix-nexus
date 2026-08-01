from typing import Literal

from langchain_core.messages import AIMessage

from app.agents.state import AgentState

_MAX_ITERATIONS = 10


def should_continue(
    state: AgentState,
) -> Literal["tools", "memory_save", "__end__"]:
    if state["iteration_count"] >= _MAX_ITERATIONS:
        return "__end__"

    last_message = state["messages"][-1] if state["messages"] else None
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"

    return "memory_save"

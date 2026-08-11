from langchain_core.messages import AIMessage, HumanMessage

from app.agents.router import should_continue
from app.agents.state import AgentState


def _make_state(**overrides) -> AgentState:
    base: AgentState = {
        "messages": [],
        "user_id": "user-1",
        "conversation_id": "conv-1",
        "user_facts": [],
        "requires_human": False,
        "human_feedback": None,
        "iteration_count": 0,
        "error": None,
        "next_agent": None,
    }
    base.update(overrides)
    return base


def test_router_goes_to_tools_when_tool_calls():
    ai_msg = AIMessage(
        content="", tool_calls=[{"name": "knowledge_base_search", "args": {}, "id": "1"}]
    )
    state = _make_state(messages=[HumanMessage(content="hi"), ai_msg])
    assert should_continue(state) == "tools"


def test_router_goes_to_memory_save_on_final_answer():
    ai_msg = AIMessage(content="Here is your answer.")
    state = _make_state(messages=[HumanMessage(content="hi"), ai_msg])
    assert should_continue(state) == "memory_save"


def test_router_ends_on_max_iterations():
    ai_msg = AIMessage(
        content="", tool_calls=[{"name": "knowledge_base_search", "args": {}, "id": "1"}]
    )
    state = _make_state(messages=[ai_msg], iteration_count=10)
    assert should_continue(state) == "__end__"


def test_router_ends_on_empty_messages():
    state = _make_state(messages=[])
    assert should_continue(state) == "memory_save"

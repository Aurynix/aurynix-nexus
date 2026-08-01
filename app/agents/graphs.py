from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.base import BaseStore

from app.agents.nodes import agent_node, execute_tools_node, memory_load_node, memory_save_node
from app.agents.router import should_continue
from app.agents.state import AgentState


def build_graph(
    checkpointer: AsyncPostgresSaver,
    store: BaseStore,
):
    workflow = StateGraph(AgentState)

    workflow.add_node("memory_load", memory_load_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", execute_tools_node)
    workflow.add_node("memory_save", memory_save_node)

    workflow.add_edge(START, "memory_load")
    workflow.add_edge("memory_load", "agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "memory_save": "memory_save",
            "__end__": END,
        },
    )
    workflow.add_edge("tools", "agent")
    workflow.add_edge("memory_save", END)

    return workflow.compile(checkpointer=checkpointer, store=store)

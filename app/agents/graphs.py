from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.base import BaseStore

from app.agents.nodes import memory_load_node, memory_save_node
from app.agents.state import AgentState
from app.agents.subagents import make_subagent_node
from app.agents.supervisor import route_supervisor, supervisor_node

_SUBAGENT_NAMES = ["research", "email", "calendar"]


def build_graph(
    checkpointer: AsyncPostgresSaver,
    store: BaseStore,
):
    workflow = StateGraph(AgentState)

    # Shared nodes
    workflow.add_node("memory_load", memory_load_node)
    workflow.add_node("memory_save", memory_save_node)
    workflow.add_node("supervisor", supervisor_node)

    # Sub-agent nodes
    for name in _SUBAGENT_NAMES:
        workflow.add_node(f"{name}_agent", make_subagent_node(name))

    # Entry: load memory then hand to supervisor
    workflow.add_edge(START, "memory_load")
    workflow.add_edge("memory_load", "supervisor")

    # Supervisor routes to a sub-agent or FINISH
    workflow.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {name: f"{name}_agent" for name in _SUBAGENT_NAMES} | {"FINISH": "memory_save"},
    )

    # Each sub-agent returns to the supervisor for re-evaluation
    for name in _SUBAGENT_NAMES:
        workflow.add_edge(f"{name}_agent", "supervisor")

    workflow.add_edge("memory_save", END)

    return workflow.compile(checkpointer=checkpointer, store=store)

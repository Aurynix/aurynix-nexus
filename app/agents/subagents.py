"""Sub-agent node factory — each agent runs a single ReAct step with its own tools."""

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from app.agents.state import AgentState
from app.core.llm import get_llm
from app.core.logging import get_logger

logger = get_logger(__name__)

_PROMPTS = {
    "research": (
        "You are a research specialist. Use knowledge_base_search to find information "
        "in the user's documents, and web_search for current or external information. "
        "Provide concise, sourced answers."
    ),
    "email": (
        "You are an email assistant. Use the gmail tool to read, search, and send emails. "
        "Always confirm before sending. Summarize retrieved emails clearly."
    ),
    "calendar": (
        "You are a calendar assistant. Use the calendar tool to list, create, or delete events. "
        "Always confirm event details before creating. Present dates in a human-friendly format."
    ),
}


def _get_tools_for_agent(agent_name: str, user_id: str, db):
    from app.tools.registry import make_tools

    all_tools = make_tools(user_id, db=db)
    tool_map = {t.name: t for t in all_tools}

    subsets = {
        "research": ["knowledge_base_search", "web_search", "request_human_input"],
        "email": ["gmail", "request_human_input"],
        "calendar": ["calendar", "request_human_input"],
    }
    names = subsets.get(agent_name, [t.name for t in all_tools])
    return [tool_map[n] for n in names if n in tool_map]


def make_subagent_node(agent_name: str):
    """Return a LangGraph node function for the given sub-agent."""

    async def subagent_node(state: AgentState, config: RunnableConfig) -> dict:
        user_id = state["user_id"]
        db = (config.get("configurable") or {}).get("db")
        tools = _get_tools_for_agent(agent_name, user_id, db)

        llm = get_llm().bind_tools(tools)
        system = SystemMessage(content=_PROMPTS.get(agent_name, "You are a helpful assistant."))

        # Run the LLM step
        response = await llm.ainvoke([system, *state["messages"]], config=config)

        messages = [response]

        # If the LLM wants to call tools, execute them immediately in the same node
        if isinstance(response, AIMessage) and response.tool_calls:
            tools_by_name = {t.name: t for t in tools}
            for tool_call in response.tool_calls:
                tool = tools_by_name.get(tool_call["name"])
                if tool is None:
                    result = f"Tool '{tool_call['name']}' is not available."
                else:
                    try:
                        result = await tool.ainvoke(tool_call["args"])
                    except Exception as exc:
                        result = f"Tool error: {exc}"

                messages.append(
                    ToolMessage(
                        content=str(result),
                        name=tool_call["name"],
                        tool_call_id=tool_call["id"],
                    )
                )

            # Stream the synthesis so tokens appear in the SSE stream
            synthesis_chunks = []
            async for chunk in llm.astream(
                [system, *state["messages"], *messages], config=config
            ):
                synthesis_chunks.append(chunk)
            synthesis = synthesis_chunks[0] if synthesis_chunks else AIMessage(content="")
            for c in synthesis_chunks[1:]:
                synthesis = synthesis + c
            messages.append(synthesis)

        logger.info("Sub-agent completed", agent=agent_name, message_count=len(messages))
        return {"messages": messages}

    subagent_node.__name__ = f"{agent_name}_agent"
    return subagent_node

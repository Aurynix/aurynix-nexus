"""Sub-agent node factory — each agent runs a single ReAct step with its own tools."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from app.agents.state import AgentState
from app.core.llm import get_llm
from app.core.logging import get_logger

logger = get_logger(__name__)

_PROMPTS = {
    "research": (
        "You are a research specialist. Answer the user's question using the knowledge base "
        "context provided below. If the context contains the answer, use it directly. "
        "If the context is empty or irrelevant, say so clearly and offer to search the web.\n\n"
        "Be concise and cite the source filename when quoting from documents."
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
        tools_by_name = {t.name: t for t in tools}

        plain_llm = get_llm()

        prompt = _PROMPTS.get(agent_name, "You are a helpful assistant.")
        facts = state.get("user_facts") or []
        if facts:
            prompt += "\n\nKnown facts about the user:\n" + "\n".join(facts)

        if agent_name == "research":
            return await _research_node(state, config, tools_by_name, plain_llm, prompt)

        # email / calendar: standard tool-calling flow
        llm_with_tools = get_llm().bind_tools(tools)
        system = SystemMessage(content=prompt)
        response = await llm_with_tools.ainvoke([system, *state["messages"]], config=config)
        messages = [response]

        if isinstance(response, AIMessage) and response.tool_calls:
            for tool_call in response.tool_calls:
                tool = tools_by_name.get(tool_call["name"])
                result = (
                    await tool.ainvoke(tool_call["args"])
                    if tool
                    else f"Tool '{tool_call['name']}' is not available."
                )
                if not isinstance(result, str):
                    result = str(result)
                messages.append(
                    ToolMessage(
                        content=result,
                        name=tool_call["name"],
                        tool_call_id=tool_call["id"],
                    )
                )

            # Synthesis with plain LLM — no tools bound so Groq returns text
            synthesis_chunks = []
            async for chunk in plain_llm.astream(
                [system, *state["messages"], *messages], config=config
            ):
                synthesis_chunks.append(chunk)
            synthesis = synthesis_chunks[0] if synthesis_chunks else AIMessage(content="")
            for c in synthesis_chunks[1:]:
                synthesis = synthesis + c
            messages.append(synthesis)

        logger.info("Sub-agent completed", agent=agent_name, message_count=len(messages))
        return {"messages": messages, "agent_responded": True}

    subagent_node.__name__ = f"{agent_name}_agent"
    return subagent_node


async def _research_node(
    state: AgentState,
    config: RunnableConfig,
    tools_by_name: dict,
    plain_llm,
    base_prompt: str,
) -> dict:
    """
    Research agent: always searches the knowledge base first (programmatically),
    injects results into the prompt, then generates the answer.
    The LLM never decides whether to search — it always does.
    """
    last_human = next((m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), None)
    query = last_human.content if last_human else ""

    # Step 1: always search the knowledge base
    kb_context = ""
    kb_tool = tools_by_name.get("knowledge_base_search")
    if kb_tool and query:
        try:
            kb_context = str(await kb_tool.ainvoke({"query": query}))
            logger.info("KB search completed", query=query[:80])
        except Exception as exc:
            logger.warning("KB search failed", error=str(exc))

    # Step 2: build prompt with KB results injected
    prompt_with_context = base_prompt
    if kb_context and kb_context != "No relevant documents found in the knowledge base.":
        prompt_with_context += (
            f"\n\n--- Knowledge base context ---\n{kb_context}\n--- End context ---"
        )
    else:
        prompt_with_context += (
            "\n\nNo relevant documents were found in the knowledge base for this query. "
            "Answer from general knowledge or suggest a web search."
        )

    system = SystemMessage(content=prompt_with_context)

    # Step 3: generate the answer (stream it so tokens appear in the SSE feed)
    synthesis_chunks = []
    async for chunk in plain_llm.astream([system, *state["messages"]], config=config):
        synthesis_chunks.append(chunk)

    response = synthesis_chunks[0] if synthesis_chunks else AIMessage(content="")
    for c in synthesis_chunks[1:]:
        response = response + c

    logger.info("Research agent completed", kb_hit=bool(kb_context))
    return {"messages": [response], "agent_responded": True}

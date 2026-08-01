from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore

from app.agents.state import AgentState
from app.core.llm import get_llm
from app.core.logging import get_logger
from app.memory.store import load_user_facts, upsert_user_fact
from app.tools.rag_tool import make_rag_tool

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are Aurynix, an AI-powered business assistant.

You help users by:
- Answering questions using their uploaded documents (use knowledge_base_search)
- Remembering important facts about the user and their work
- Providing thoughtful, accurate responses

User context:
{user_facts}

Be concise, accurate, and helpful. If you use the knowledge base, cite the source document.
"""


async def execute_tools_node(state: AgentState) -> dict:
    """Custom tool executor that creates per-user tools from state."""
    user_id = state["user_id"]
    rag_tool = make_rag_tool(user_id)
    tools_by_name = {rag_tool.name: rag_tool}

    last_message = state["messages"][-1]
    tool_messages: list[ToolMessage] = []

    for tool_call in getattr(last_message, "tool_calls", []):
        tool = tools_by_name.get(tool_call["name"])
        if tool is None:
            result = f"Tool '{tool_call['name']}' is not available."
        else:
            try:
                result = await tool.ainvoke(tool_call["args"])
            except Exception as exc:
                result = f"Tool error: {exc}"

        tool_messages.append(
            ToolMessage(
                content=str(result),
                name=tool_call["name"],
                tool_call_id=tool_call["id"],
            )
        )

    return {"messages": tool_messages}


async def memory_load_node(state: AgentState, store: BaseStore) -> dict:
    user_id = state["user_id"]
    facts = await load_user_facts(user_id, store)
    return {"user_facts": facts}


async def agent_node(state: AgentState, config: RunnableConfig) -> dict:
    user_id = state["user_id"]
    rag_tool = make_rag_tool(user_id)

    llm = get_llm().bind_tools([rag_tool])

    facts_text = "\n".join(state["user_facts"]) if state["user_facts"] else "No facts stored yet."
    system = SystemMessage(content=_SYSTEM_PROMPT.format(user_facts=facts_text))

    messages = [system, *state["messages"]]
    response = await llm.ainvoke(messages, config=config)

    return {
        "messages": [response],
        "iteration_count": state["iteration_count"] + 1,
    }


async def memory_save_node(state: AgentState, store: BaseStore) -> dict:
    user_id = state["user_id"]
    messages = state["messages"]

    if len(messages) < 2:
        return {}

    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    if not last_human:
        return {}

    extraction_prompt = (
        "From this user message, extract any personal facts worth remembering "
        "(name, role, preferences, important context). Return ONLY a JSON object "
        "with key-value pairs of facts, or {} if nothing notable. "
        'Example: {"name": "Alice", "role": "product manager"}\n\n'
        f"User message: {last_human.content}"
    )

    try:
        import json

        result = await get_llm().ainvoke([HumanMessage(content=extraction_prompt)])
        text = result.content.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            facts = json.loads(text[start:end])
            for key, value in facts.items():
                await upsert_user_fact(user_id, key, str(value), 0.9, store)
            if facts:
                logger.info("Memory facts saved", user_id=user_id, count=len(facts))
    except Exception as exc:
        logger.warning("Memory extraction failed", error=str(exc))

    return {}

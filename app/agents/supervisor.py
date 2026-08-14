"""Supervisor node — decides which sub-agent handles the next step."""

from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from app.agents.state import AgentState
from app.core.llm import get_llm
from app.core.logging import get_logger

logger = get_logger(__name__)

_SUBAGENTS = Literal["research", "email", "calendar", "FINISH"]

_MAX_ITERATIONS = 6


class SupervisorDecision(BaseModel):
    next: _SUBAGENTS
    reasoning: str


_SUPERVISOR_PROMPT = """You are a supervisor orchestrating specialized AI agents.

Available agents:
- research: Handles all conversations, questions, greetings, and document/web searches
- email: Reads and sends emails via Gmail
- calendar: Lists and manages Google Calendar events
- FINISH: End ONLY after an agent has already replied to the user

Current user facts:
{user_facts}

Rules:
1. ALWAYS route to an agent first — never choose FINISH as the first action.
2. Choose FINISH only after an agent has already produced a response.
3. Use "research" for everything that isn't clearly email or calendar related — including greetings and chat.
4. Use "email" only when the user explicitly mentions email or Gmail.
5. Use "calendar" only when the user explicitly mentions calendar or scheduling.

Respond with valid JSON only, in this exact format:
{{"next": "<agent_name>", "reasoning": "<brief reason>"}}
"""


async def supervisor_node(state: AgentState, config: RunnableConfig) -> dict:
    if state["iteration_count"] >= _MAX_ITERATIONS:
        return {"next_agent": "FINISH", "iteration_count": state["iteration_count"] + 1}

    messages = state.get("messages") or []

    # If the last message is already an AI response, the sub-agent has answered — stop.
    if messages and isinstance(messages[-1], AIMessage) and not messages[-1].tool_calls:
        return {"next_agent": "FINISH", "iteration_count": state["iteration_count"] + 1}

    # If the last message is from the user, we must call an agent (never FINISH first).
    must_call_agent = messages and isinstance(messages[-1], HumanMessage)

    facts_text = "\n".join(state["user_facts"]) if state["user_facts"] else "None"
    system = SystemMessage(content=_SUPERVISOR_PROMPT.format(user_facts=facts_text))

    llm = get_llm().with_structured_output(SupervisorDecision, method="json_mode")

    try:
        decision: SupervisorDecision = await llm.ainvoke([system, *state["messages"]])
        logger.info(
            "Supervisor decision",
            next=decision.next,
            reasoning=decision.reasoning[:100],
        )
        next_agent = decision.next
        if must_call_agent and next_agent == "FINISH":
            next_agent = "research"
        return {
            "next_agent": next_agent,
            "iteration_count": state["iteration_count"] + 1,
        }
    except Exception as exc:
        logger.error("Supervisor failed", error=str(exc))
        return {"next_agent": "FINISH", "iteration_count": state["iteration_count"] + 1}


def route_supervisor(state: AgentState) -> str:
    return state.get("next_agent") or "FINISH"

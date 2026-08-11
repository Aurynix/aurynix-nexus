"""Supervisor node — decides which sub-agent handles the next step."""

from typing import Literal

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from app.agents.state import AgentState
from app.core.llm import get_llm
from app.core.logging import get_logger

logger = get_logger(__name__)

_SUBAGENTS = Literal["research", "email", "calendar", "FINISH"]

_MAX_ITERATIONS = 15


class SupervisorDecision(BaseModel):
    next: _SUBAGENTS
    reasoning: str


_SUPERVISOR_PROMPT = """You are a supervisor orchestrating specialized AI agents.

Available agents:
- research: Searches the user's documents and the web to answer questions
- email: Reads and sends emails via Gmail
- calendar: Lists and manages Google Calendar events
- FINISH: End the conversation — use this when the task is complete

Current user facts:
{user_facts}

Based on the conversation so far, decide which agent should act next.
If the task is done or no tool use is needed, choose FINISH.
"""


async def supervisor_node(state: AgentState, config: RunnableConfig) -> dict:
    if state["iteration_count"] >= _MAX_ITERATIONS:
        return {"next_agent": "FINISH", "iteration_count": state["iteration_count"] + 1}

    facts_text = "\n".join(state["user_facts"]) if state["user_facts"] else "None"
    system = SystemMessage(content=_SUPERVISOR_PROMPT.format(user_facts=facts_text))

    llm = get_llm().with_structured_output(SupervisorDecision)

    try:
        decision: SupervisorDecision = await llm.ainvoke([system, *state["messages"]])
        logger.info(
            "Supervisor decision",
            next=decision.next,
            reasoning=decision.reasoning[:100],
        )
        return {
            "next_agent": decision.next,
            "iteration_count": state["iteration_count"] + 1,
        }
    except Exception as exc:
        logger.error("Supervisor failed", error=str(exc))
        return {"next_agent": "FINISH", "iteration_count": state["iteration_count"] + 1}


def route_supervisor(state: AgentState) -> str:
    return state.get("next_agent") or "FINISH"

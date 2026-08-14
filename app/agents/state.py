from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    conversation_id: str
    user_facts: list[str]
    requires_human: bool
    human_feedback: str | None
    iteration_count: int
    error: str | None
    # Multi-agent routing — set by the supervisor, consumed by sub-agent nodes
    next_agent: str | None
    # Set to True by any sub-agent that produces a user-facing response
    agent_responded: bool

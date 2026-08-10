"""Human handoff tool — interrupts the agent and waits for human input via SSE."""
from langchain_core.tools import tool
from langgraph.types import interrupt


@tool
async def request_human_input(question: str) -> str:
    """
    Pause the conversation and ask a human for clarification or approval.
    Use this when the task is ambiguous, risky, or requires human judgment.
    The question will be sent to the user and the agent will wait for their response.
    """
    human_response = interrupt({"question": question})
    return str(human_response)

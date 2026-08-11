from langchain_core.tools import BaseTool
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.human_handoff import request_human_input
from app.tools.rag_tool import make_rag_tool
from app.tools.web_search import web_search


def make_tools(user_id: str, db: AsyncSession | None = None) -> list[BaseTool]:
    """Return all tools available for the given user.

    db is required for Gmail and Calendar tools; omit for testing or
    contexts where Google tools are not needed.
    """
    tools: list[BaseTool] = [
        make_rag_tool(user_id),
        web_search,
        request_human_input,
    ]

    if db is not None:
        from app.tools.calendar import make_calendar_tool
        from app.tools.gmail import make_gmail_tool

        tools.append(make_gmail_tool(user_id, db))
        tools.append(make_calendar_tool(user_id, db))

    return tools

from langchain_core.tools import BaseTool

from app.tools.rag_tool import make_rag_tool
from app.tools.web_search import web_search


def make_tools(user_id: str) -> list[BaseTool]:
    """Return all tools available for the given user."""
    return [
        make_rag_tool(user_id),
        web_search,
    ]

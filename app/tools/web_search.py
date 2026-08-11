import asyncio

from langchain_core.tools import tool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@tool
async def web_search(query: str) -> str:
    """
    Search the web for current information: news, prices, weather, documentation,
    or anything not available in the user's uploaded documents.
    Use this when the question requires up-to-date or real-time information.
    """
    if not settings.tavily_api_key:
        return "Web search is not configured (TAVILY_API_KEY is missing)."

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=settings.tavily_api_key)
        response = await asyncio.to_thread(
            client.search,
            query,
            max_results=5,
            search_depth="advanced",
        )
        results = response.get("results", [])
        if not results:
            return "No results found for this query."

        lines: list[str] = []
        for i, r in enumerate(results, 1):
            lines.append(f"[{i}] {r['title']}")
            lines.append(f"    URL: {r['url']}")
            lines.append(f"    {r.get('content', '')[:300]}")
            lines.append("")

        logger.info("Web search completed", query=query, result_count=len(results))
        return "\n".join(lines).strip()

    except Exception as exc:
        logger.error("Web search failed", query=query, error=str(exc))
        return f"Web search failed: {exc}"

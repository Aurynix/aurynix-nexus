from langchain_core.tools import BaseTool, tool

from app.rag.pipeline import RAGPipeline


def make_rag_tool(user_id: str) -> BaseTool:
    """
    Factory that creates a per-request RAG tool closed over the caller's user_id.
    This avoids global state and ensures each user only searches their own documents.
    """
    pipeline = RAGPipeline()

    @tool
    async def knowledge_base_search(query: str) -> str:
        """
        Search the user's uploaded document knowledge base.
        Use this tool to answer questions about documents the user has uploaded.
        Returns relevant text excerpts from matching documents.
        """
        docs = await pipeline.query(query, user_id=user_id)
        if not docs:
            return "No relevant documents found in the knowledge base."
        sections = []
        for doc in docs:
            filename = doc.metadata.get("filename", "unknown")
            sections.append(f"[Source: {filename}]\n{doc.page_content}")
        return "\n\n---\n\n".join(sections)

    return knowledge_base_search

from langchain_groq import ChatGroq

from app.core.config import get_settings

_llm: ChatGroq | None = None


def get_llm() -> ChatGroq:
    global _llm
    if _llm is None:
        s = get_settings()
        _llm = ChatGroq(
            model=s.model_name,
            groq_api_key=s.groq_api_key,
            temperature=0.2,
        )
    return _llm

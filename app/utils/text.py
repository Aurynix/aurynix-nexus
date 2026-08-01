import re


def truncate(text: str, max_chars: int = 500, suffix: str = "...") -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars - len(suffix)] + suffix


def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_json_block(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return text[start:end]
    return None

from pathlib import Path

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document

from app.core.exceptions import DocumentProcessingError
from app.core.logging import get_logger

logger = get_logger(__name__)

_SUPPORTED = {".pdf", ".docx", ".txt"}


def load(file_path: Path) -> list[Document]:
    suffix = file_path.suffix.lower()
    if suffix not in _SUPPORTED:
        raise DocumentProcessingError(f"Unsupported file type: {suffix}")

    try:
        if suffix == ".pdf":
            loader = PyPDFLoader(str(file_path))
        elif suffix == ".docx":
            loader = Docx2txtLoader(str(file_path))
        else:
            loader = TextLoader(str(file_path), encoding="utf-8")

        docs = loader.load()
        logger.info("Document loaded", path=str(file_path), pages=len(docs))
        return docs
    except Exception as exc:
        raise DocumentProcessingError(f"Failed to load {file_path.name}: {exc}") from exc

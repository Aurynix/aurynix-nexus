from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


class DocumentChunker:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200) -> None:
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
        )

    def chunk(self, docs: list[Document], doc_id: str, user_id: str) -> list[Document]:
        chunks = self._splitter.split_documents(docs)
        for chunk in chunks:
            chunk.metadata["doc_id"] = doc_id
            chunk.metadata["user_id"] = user_id
        return chunks

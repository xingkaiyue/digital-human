import hashlib
from dataclasses import dataclass
from typing import List, Sequence

from .chunker.schema import DocumentChunk
from .embedding import SentenceEmbedder
from .vectorstore import ChromaStore


@dataclass(frozen=True)
class IngestedBatch:
    documents: List[str]
    metadatas: List[dict]
    ids: List[str]
    embeddings: List[List[float]]


class Pipeline:
    def __init__(self, embed_model: SentenceEmbedder, store: ChromaStore):
        self.embed_model = embed_model
        self.store = store

    def run(self, chunks: Sequence[DocumentChunk], batch_size: int = 32) -> int:
        normalized = [chunk for chunk in chunks if chunk.text.strip()]
        if not normalized:
            return 0

        total = 0
        for start in range(0, len(normalized), batch_size):
            batch = normalized[start : start + batch_size]
            payload = self._build_batch(batch)
            self.store.upsert(
                documents=payload.documents,
                embeddings=payload.embeddings,
                metadatas=payload.metadatas,
                ids=payload.ids,
            )
            total += len(batch)
        return total

    def _build_batch(self, chunks: Sequence[DocumentChunk]) -> IngestedBatch:
        documents = [chunk.text for chunk in chunks]
        metadatas = [dict(chunk.metadata or {}) for chunk in chunks]
        ids = [self._stable_chunk_id(chunk) for chunk in chunks]
        embeddings = self.embed_model.embed_documents(documents)
        return IngestedBatch(documents=documents, metadatas=metadatas, ids=ids, embeddings=embeddings)

    @staticmethod
    def _stable_chunk_id(chunk: DocumentChunk) -> str:
        source = str(chunk.metadata.get("file_path") or chunk.metadata.get("source") or "unknown")
        start = str(chunk.metadata.get("start", "0"))
        raw = f"{source}:{chunk.chunk_id}:{start}:{chunk.text}"
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
        return f"{chunk.chunk_id}-{digest}"

from typing import List
from knowledge.chunker.schema import Document, DocumentChunk


class TextChunker:
    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, document: Document) -> List[DocumentChunk]:
        text = document.text.strip()
        chunks: List[DocumentChunk] = []

        if not text:
            return chunks

        start = 0
        chunk_id = 0
        length = len(text)

        while start < length:
            end = start + self.chunk_size
            chunk_text = text[start:end]

            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    text=chunk_text,
                    metadata={
                        **document.metadata,
                        "start": start,
                        "end": min(end, length),
                    },
                )
            )

            chunk_id += 1
            start = end - self.overlap

            if start < 0:
                start = 0

        return chunks
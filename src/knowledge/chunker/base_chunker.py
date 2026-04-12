from abc import ABC, abstractmethod
from typing import List
from .schema import Document, DocumentChunk


class BaseChunker(ABC):

    @abstractmethod
    def split(self, document: Document) -> List[DocumentChunk]:
        pass
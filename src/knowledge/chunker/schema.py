from dataclasses import dataclass
from typing import Dict, Any, List


@dataclass
class Document:
    text: str
    metadata: Dict[str, Any]


@dataclass
class DocumentChunk:
    chunk_id: int
    text: str
    metadata: Dict[str, Any]
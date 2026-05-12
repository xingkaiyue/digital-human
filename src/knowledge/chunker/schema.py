from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(slots=True)
class Document:
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DocumentChunk:
    chunk_id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)

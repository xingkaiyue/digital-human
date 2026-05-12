from dataclasses import dataclass
from typing import List, Optional, Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    finish_reason: Optional[str] = None


class LLMClient(Protocol):
    provider: str
    model: str

    def chat(self, messages: List[ChatMessage]) -> LLMResponse:
        ...

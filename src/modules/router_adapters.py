from __future__ import annotations

from typing import Any, Dict, List, Optional


class KnowledgeRetrieverAdapter:
    def __init__(self, knowledge_service: Any):
        self.knowledge_service = knowledge_service

    def search(
        self,
        query: str,
        scene_context: Optional[Any] = None,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        results = self.knowledge_service.search(
            query=query,
            scene_context=scene_context,
            top_k=top_k,
        )

        normalized: List[Dict[str, Any]] = []
        for item in results:
            text = getattr(item, "text", "")
            metadata = getattr(item, "metadata", {}) or {}
            score = getattr(item, "score", 0.0)

            normalized.append(
                {
                    "text": text,
                    "metadata": metadata,
                    "score": score,
                }
            )
        return normalized

    def retrieve(
        self,
        query: str,
        scene_context: Optional[Any] = None,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        return self.search(
            query=query,
            scene_context=scene_context,
            top_k=top_k,
        )


class LLMAggregatorAdapter:
    def __init__(self, llm_client: Any):
        self.llm_client = llm_client

    def chat(self, messages: List[Dict[str, str]]) -> str:
        # 兼容你现有 OpenAICompatibleClient.chat(messages=[...]) 的用法
        from llm.base import ChatMessage

        chat_messages = [
            ChatMessage(role=item["role"], content=item["content"])
            for item in messages
        ]
        response = self.llm_client.chat(chat_messages)
        return response.content

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        from llm.base import ChatMessage

        response = self.llm_client.chat(
            [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt),
            ]
        )
        return response.content

    def complete(self, prompt: str) -> str:
        from llm.base import ChatMessage

        response = self.llm_client.chat(
            [ChatMessage(role="user", content=prompt)]
        )
        return response.content

import re
from typing import Iterable, List, Optional, Sequence

from .retriever import RetrievalResult


def _tokenize(text: str) -> List[str]:
    normalized = re.sub(r"\s+", "", text.lower())
    english_tokens = re.findall(r"[a-z0-9]+", normalized)

    chinese_bigrams = []
    for i in range(len(normalized) - 1):
        if "\u4e00" <= normalized[i] <= "\u9fff":
            chinese_bigrams.append(normalized[i : i + 2])

    return english_tokens + chinese_bigrams


def _lexical_overlap(query_tokens: Sequence[str], text_tokens: Sequence[str]) -> float:
    if not query_tokens or not text_tokens:
        return 0.0
    query_set = set(query_tokens)
    text_set = set(text_tokens)
    return len(query_set & text_set) / max(len(query_set), 1)


class HybridReranker:
    def rerank(
        self,
        query: str,
        results: Iterable[RetrievalResult],
        top_k: int = 4,
        prefer_structured: bool = False,
        scenic_name: Optional[str] = None,
    ) -> List[RetrievalResult]:
        query_tokens = _tokenize(query)
        reranked: List[RetrievalResult] = []

        for result in results:
            metadata = result.metadata or {}
            text_tokens = _tokenize(result.text)
            lexical_score = _lexical_overlap(query_tokens, text_tokens)

            final_score = result.score * 0.60 + lexical_score * 0.40

            chunk_type = str(metadata.get("chunk_type", "")).strip()
            scenic = str(metadata.get("scenic_name", "") or metadata.get("景区名称", "")).strip()

            if prefer_structured and chunk_type == "structured_spot":
                final_score += 0.15

            if scenic_name and scenic == scenic_name:
                final_score += 0.18

            reranked.append(
                RetrievalResult(
                    text=result.text,
                    metadata=metadata,
                    distance=result.distance,
                    score=final_score,
                )
            )

        reranked.sort(key=lambda item: item.score, reverse=True)

        deduped: List[RetrievalResult] = []
        seen = set()

        for item in reranked:
            metadata = item.metadata or {}
            key = (
                metadata.get("spot_key")
                or metadata.get("spot_id")
                or metadata.get("景点ID")
                or metadata.get("spot_name")
                or metadata.get("景点名称")
                or metadata.get("text_preview")
                or item.text[:80]
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        return deduped[:top_k]

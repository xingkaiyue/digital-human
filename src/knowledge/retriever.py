from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .embedding import SentenceEmbedder
from .scene_context import SceneContext
from .vectorstore import ChromaStore


@dataclass(frozen=True)
class RetrievalResult:
    text: str
    metadata: Dict[str, Any]
    distance: float
    score: float


class VectorRetriever:
    def __init__(
        self,
        embed_model: SentenceEmbedder,
        store: ChromaStore,
        collection_role: str,
    ):
        self.embed_model = embed_model
        self.store = store
        self.collection_role = collection_role

    def search(
        self,
        query: str,
        scene_context: Optional[SceneContext] = None,
        top_k: int = 4,
    ) -> List[RetrievalResult]:
        # 列举景点：直接从 structured 里全量拉，再按景区名强过滤
        if self.collection_role == "structured" and self._is_list_spots_query(query):
            return self._list_spot_results(
                query=query,
                scene_context=scene_context,
                top_k=max(top_k, 50),
            )

        where = self._build_where(scene_context)
        query_embedding = self.embed_model.embed_query(query)

        raw_matches = self.store.similarity_search(
            query_embedding=query_embedding,
            top_k=max(top_k, top_k * 3) if self.collection_role == "structured" else top_k,
            where=where,
        )

        results = [
            RetrievalResult(
                text=match["text"],
                metadata=match.get("metadata", {}),
                distance=float(match.get("distance", 0.0)),
                score=1.0 / (1.0 + float(match.get("distance", 0.0))),
            )
            for match in raw_matches
        ]

        if self.collection_role == "structured":
            results = self._filter_results_by_scenic_name(
                results=results,
                query=query,
                scene_context=scene_context,
            )
            results = self._dedupe_results(results)

        return results[:top_k]

    def _build_where(self, scene_context: Optional[SceneContext]) -> Optional[Dict[str, Any]]:
        conditions: List[Dict[str, Any]] = []

        if self.collection_role == "structured":
            conditions.append({"chunk_type": "structured_spot"})

        # 保守起见：这里先不对 structured 再做 scenic_id/destination_id 限制
        # 因为当前 spot 级 metadata 是否完整继承这些字段还不确定
        if self.collection_role != "structured" and scene_context:
            scenic_id = scene_context.resolve_filter_scenic_id()
            destination_id = scene_context.resolve_filter_destination_id()

            if scenic_id:
                conditions.append({"scenic_id": scenic_id})
            elif destination_id:
                conditions.append({"destination_id": destination_id})

        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    def _list_spot_results(
            self,
            query: str,
            scene_context: Optional[SceneContext],
            top_k: int,
    ) -> List[RetrievalResult]:
        print(f"[DEBUG retriever] _list_spot_results called, query={query}")

        where = self._build_where(scene_context)
        items = self.store.get_all(where=where)

        target_scenic_name = self._resolve_target_scenic_name(
            query=query,
            scene_context=scene_context,
        )

        if target_scenic_name:
            items = [
                item
                for item in items
                if self._normalize_scenic_name(
                    (item.get('metadata', {}) or {}).get('景区名称')
                ) == target_scenic_name
            ]

        print(f"[DEBUG retriever] target_scenic_name={target_scenic_name}, filtered_count={len(items)}")

        deduped_items: List[Dict[str, Any]] = []
        seen = set()

        for item in items:
            metadata = item.get("metadata", {}) or {}
            key = (
                metadata.get("spot_key")
                or metadata.get("spot_id")
                or metadata.get("景点ID")
                or metadata.get("spot_name")
                or metadata.get("景点名称")
            )
            if not key or key in seen:
                continue
            seen.add(key)
            deduped_items.append(item)

        deduped_items.sort(
            key=lambda x: (
                str((x.get("metadata", {}) or {}).get("景点ID", "")),
                int((x.get("metadata", {}) or {}).get("chunk_index", 0)),
                str((x.get("metadata", {}) or {}).get("景点名称", "")),
            )
        )

        return [
            RetrievalResult(
                text=item["text"],
                metadata=item.get("metadata", {}),
                distance=0.0,
                score=1.0,
            )
            for item in deduped_items[:top_k]
        ]

    def _filter_results_by_scenic_name(
        self,
        results: List[RetrievalResult],
        query: str,
        scene_context: Optional[SceneContext],
    ) -> List[RetrievalResult]:
        target_scenic_name = self._resolve_target_scenic_name(
            query=query,
            scene_context=scene_context,
        )
        if not target_scenic_name:
            return results

        filtered = []
        for item in results:
            scenic_name = self._normalize_scenic_name(item.metadata.get("景区名称"))
            if scenic_name == target_scenic_name:
                filtered.append(item)

        return filtered

    def _resolve_target_scenic_name(
        self,
        query: str,
        scene_context: Optional[SceneContext],
    ) -> Optional[str]:
        scenic_name = None
        destination_name = None

        if scene_context:
            scenic_name = getattr(scene_context, "scenic_name", None)
            destination_name = getattr(scene_context, "destination_name", None)

        candidate = scenic_name or destination_name or self._extract_scenic_name_from_query(query)
        return self._normalize_scenic_name(candidate)

    def _dedupe_results(self, results: List[RetrievalResult]) -> List[RetrievalResult]:
        deduped: List[RetrievalResult] = []
        seen = set()

        for item in results:
            metadata = item.metadata or {}
            key = (
                metadata.get("spot_key")
                or metadata.get("spot_id")
                or metadata.get("景点ID")
                or metadata.get("spot_name")
                or metadata.get("景点名称")
            )
            if not key:
                deduped.append(item)
                continue
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        return deduped

    @staticmethod
    def _normalize_scenic_name(name: Optional[str]) -> Optional[str]:
        if not name:
            return None

        name = str(name).strip()
        alias_map = {
            "灵山胜境": "灵山胜境",
            "拈花湾": "拈花湾禅意小镇",
            "拈花湾禅意小镇": "拈花湾禅意小镇",
        }
        return alias_map.get(name, name)

    def _extract_scenic_name_from_query(self, query: str) -> Optional[str]:
        alias_map = {
            "灵山胜境": "灵山胜境",
            "拈花湾": "拈花湾禅意小镇",
            "拈花湾禅意小镇": "拈花湾禅意小镇",
        }
        for alias, canonical_name in alias_map.items():
            if alias in query:
                return canonical_name
        return None

    @staticmethod
    def _is_list_spots_query(query: str) -> bool:
        patterns = [
            "有什么景点",
            "有哪些景点",
            "景点有哪些",
            "全部景点",
            "所有景点",
            "主要景点",
            "核心景点",
            "值得去的景点",
            "有哪些值得去",
        ]
        return any(pattern in query for pattern in patterns)

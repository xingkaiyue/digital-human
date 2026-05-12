from __future__ import annotations

from typing import Any, Dict, List, Optional

import chromadb


def _coerce_metadata_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [
            item if isinstance(item, (str, int, float, bool)) else str(item)
            for item in value
        ]
    return str(value)


def _normalize_where(where: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    把业务侧的简写 where 转成当前 Chroma 可接受的格式。

    例如：
    {"chunk_type": "structured_spot", "scenic_id": "lingshan_core"}

    转成：
    {
        "$and": [
            {"chunk_type": {"$eq": "structured_spot"}},
            {"scenic_id": {"$eq": "lingshan_core"}}
        ]
    }
    """
    if not where:
        return None

    if not isinstance(where, dict):
        raise ValueError(f"where 必须是 dict，实际收到: {type(where)}")

    # 已经是逻辑表达式，直接返回
    if any(key.startswith("$") for key in where.keys()):
        return where

    items = []
    for key, value in where.items():
        if value is None:
            continue

        # 已经是操作符格式，比如 {"score": {"$gte": 0.8}}
        if isinstance(value, dict) and any(str(k).startswith("$") for k in value.keys()):
            items.append({key: value})
            continue

        # 普通标量 / 列表
        if isinstance(value, list):
            items.append({key: {"$in": value}})
        else:
            items.append({key: {"$eq": value}})

    if not items:
        return None

    if len(items) == 1:
        return items[0]

    return {"$and": items}


class ChromaStore:
    def __init__(self, persist_dir: str, collection_name: str = "rag_collection"):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def upsert(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
        ids: List[str],
    ) -> None:
        if not (len(documents) == len(embeddings) == len(metadatas) == len(ids)):
            raise ValueError("documents / embeddings / metadatas / ids 长度不一致")

        normalized_metadatas = []
        for index, metadata in enumerate(metadatas):
            item = {
                key: _coerce_metadata_value(value)
                for key, value in dict(metadata or {}).items()
            }
            item.setdefault("chunk_index", index)
            item.setdefault("text_preview", documents[index][:80])
            normalized_metadatas.append(item)

        self.collection.upsert(
            documents=documents,
            embeddings=embeddings,
            metadatas=normalized_metadatas,
            ids=ids,
        )

    def similarity_search(
        self,
        query_embedding: List[float],
        top_k: int = 4,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        normalized_where = _normalize_where(where)

        query_kwargs: Dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if normalized_where:
            query_kwargs["where"] = normalized_where

        results = self.collection.query(**query_kwargs)

        matches: List[Dict[str, Any]] = []
        for document, metadata, distance in zip(
            results.get("documents", [[]])[0],
            results.get("metadatas", [[]])[0],
            results.get("distances", [[]])[0],
        ):
            matches.append(
                {
                    "text": document,
                    "metadata": metadata or {},
                    "distance": float(distance),
                }
            )

        return matches

    def get(
        self,
        limit: int = 10,
        include: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return self.collection.get(limit=limit, include=include or ["documents", "metadatas"])

    def get_all_by_filter(
        self,
        where: Optional[Dict[str, Any]] = None,
        include: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        normalized_where = _normalize_where(where)

        get_kwargs: Dict[str, Any] = {
            "include": include or ["documents", "metadatas"],
        }
        if normalized_where:
            get_kwargs["where"] = normalized_where
        if limit is not None:
            get_kwargs["limit"] = limit

        result = self.collection.get(**get_kwargs)
        return result

    def count(self) -> int:
        return int(self.collection.count())

    def reset(self) -> None:
        self.client.delete_collection(self.collection.name)
        self.collection = self.client.get_or_create_collection(name=self.collection.name)

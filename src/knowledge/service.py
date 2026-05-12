from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import AppSettings
from llm import ChatMessage, build_llm_client

from .chunker import DocumentChunk, StructuredDocxChunker, TextChunker
from .embedding import SentenceEmbedder
from .loader import TextLoader
from .pipeline import Pipeline
from .reranker import HybridReranker
from .retriever import RetrievalResult, VectorRetriever
from .scene_context import SceneContext
from .vectorstore import ChromaStore


@dataclass(frozen=True)
class RagAnswer:
    question: str
    answer: str
    contexts: List[RetrievalResult]
    model: str


class RagKnowledgeService:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.loader = TextLoader()
        self.text_chunker = TextChunker(
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
        )
        self.structured_chunker = StructuredDocxChunker()
        self.embedder = SentenceEmbedder(
            model_path=str(settings.embedding_model_path),
            batch_size=settings.embedding_batch_size,
        )
        self.guide_store = ChromaStore(
            persist_dir=str(settings.chroma_dir),
            collection_name=settings.guide_collection,
        )
        self.structured_store = ChromaStore(
            persist_dir=str(settings.chroma_dir),
            collection_name=settings.structured_collection,
        )
        self.guide_pipeline = Pipeline(embed_model=self.embedder, store=self.guide_store)
        self.structured_pipeline = Pipeline(embed_model=self.embedder, store=self.structured_store)

        self.guide_retriever = VectorRetriever(
            embed_model=self.embedder,
            store=self.guide_store,
            collection_role="guide",
        )
        self.structured_retriever = VectorRetriever(
            embed_model=self.embedder,
            store=self.structured_store,
            collection_role="structured",
        )

        self.reranker = HybridReranker()

    # =========================
    # 入库
    # =========================
    def ingest_file(
        self,
        file_path: str,
        destination_id: Optional[str] = None,
        destination_name: Optional[str] = None,
        scenic_id: Optional[str] = None,
        scenic_name: Optional[str] = None,
        doc_type: Optional[str] = None,
        batch_size: int | None = None,
    ) -> List[DocumentChunk]:
        document = self.loader.load(file_path)

        if destination_id:
            document.metadata["destination_id"] = destination_id
        if destination_name:
            document.metadata["destination_name"] = destination_name
        if scenic_id:
            document.metadata["scenic_id"] = scenic_id
        if scenic_name:
            document.metadata["scenic_name"] = scenic_name
        if doc_type:
            document.metadata["doc_type"] = doc_type

        is_structured = (
            doc_type == "structured_spots"
            or (doc_type is None and self._is_structured_doc(document))
        )

        if is_structured:
            chunks = self.structured_chunker.split(document)
            self.structured_pipeline.run(
                chunks,
                batch_size=batch_size or self.settings.embedding_batch_size,
            )
        else:
            chunks = self.text_chunker.split(document)
            self.guide_pipeline.run(
                chunks,
                batch_size=batch_size or self.settings.embedding_batch_size,
            )

        return chunks

    def ingest_directory(
        self,
        directory: str,
        destination_id: Optional[str] = None,
        destination_name: Optional[str] = None,
        scenic_id: Optional[str] = None,
        scenic_name: Optional[str] = None,
        doc_type: Optional[str] = None,
    ) -> int:
        root = Path(directory).resolve()
        if not root.exists():
            raise FileNotFoundError(f"目录不存在: {root}")

        files = []
        for suffix in TextLoader.SUPPORTED_SUFFIXES:
            files.extend(root.rglob(f"*{suffix}"))

        total = 0
        for file_path in sorted(set(files)):
            chunks = self.ingest_file(
                file_path=str(file_path),
                destination_id=destination_id,
                destination_name=destination_name,
                scenic_id=scenic_id,
                scenic_name=scenic_name,
                doc_type=doc_type,
            )
            total += len(chunks)
        return total

    # =========================
    # 检索
    # =========================
    def search(
        self,
        query: str,
        scene_context: Optional[SceneContext] = None,
        top_k: int | None = None,
    ) -> List[RetrievalResult]:
        if self._is_full_spot_list_query(query):
            return self.list_spots(scene_context=scene_context, limit=None)

        prefer_structured = self._prefer_structured(query)
        recall_k = self.settings.retrieval_recall_k
        effective_top_k = top_k or (8 if prefer_structured else self.settings.retrieval_top_k)

        # 注意：这里先不把 scene_context 直接传给 structured_retriever，
        # 因为当前结构化总表是“一个文档里混多个景区”，
        # spot 级过滤要按 metadata["景区名称"] 做，而不是按 doc 级 scenic_id 做。
        structured_results = self.structured_retriever.search(query=query, top_k=recall_k)
        guide_results = self.guide_retriever.search(
            query=query,
            scene_context=scene_context,
            top_k=recall_k,
        )

        structured_results = [
            item for item in structured_results
            if self._matches_scene_context(item.metadata, scene_context, is_structured=True)
        ]
        guide_results = [
            item for item in guide_results
            if self._matches_scene_context(item.metadata, scene_context, is_structured=False)
        ]

        if prefer_structured:
            merged = structured_results + guide_results[: max(2, recall_k // 2)]
        else:
            merged = guide_results + structured_results[: max(2, recall_k // 2)]

        return self.reranker.rerank(
            query=query,
            results=merged,
            top_k=effective_top_k,
            prefer_structured=prefer_structured,
        )

    def list_spots(
        self,
        scene_context: Optional[SceneContext] = None,
        limit: Optional[int] = None,
    ) -> List[RetrievalResult]:
        where = self._build_where_for_scene(
            scene_context=scene_context,
            chunk_type="structured_spot",
        )

        raw = self.structured_store.get_all_by_filter(
            where=where,
            include=["documents", "metadatas"],
        )

        documents = raw.get("documents", []) or []
        metadatas = raw.get("metadatas", []) or []

        results: List[RetrievalResult] = []
        for doc, metadata in zip(documents, metadatas):
            metadata = metadata or {}

            # 关键修复：结构化景点列表按“景区名称”过滤，而不是按 scenic_id 过滤
            if not self._matches_scene_context(metadata, scene_context, is_structured=True):
                continue

            text = self._build_spot_summary(metadata, doc)
            results.append(
                RetrievalResult(
                    text=text,
                    metadata=metadata,
                    distance=0.0,
                    score=1.0,
                )
            )

        results.sort(key=lambda item: self._spot_sort_key(item.metadata))

        if limit is not None:
            results = results[:limit]

        return results

    # =========================
    # 问答
    # =========================
    def build_context(
        self,
        query: str,
        scene_context: Optional[SceneContext] = None,
        top_k: int | None = None,
    ) -> str:
        results = self.search(query=query, scene_context=scene_context, top_k=top_k)
        return self._build_context_from_results(results)

    def answer(
        self,
        question: str,
        scene_context: Optional[SceneContext] = None,
        top_k: int | None = None,
    ) -> RagAnswer:
        contexts = self.search(question, scene_context=scene_context, top_k=top_k)
        context_text = self._build_context_from_results(contexts)
        llm = build_llm_client(self.settings)

        system_prompt = (
            "你是一个检索增强问答助手。"
            "你只能基于提供的资料片段回答问题。"
            "如果资料不足以回答，就明确说资料不足，不要编造。"
            "回答时优先给出准确结论，再补充关键依据。"
            "如果资料中包含多个景点、项目或条目，请尽量完整列举，不要只举两个例子。"
            "如果检索结果中有结构化景点资料，优先综合其中的景点名称、位置和亮点。"
            "如果问题是在问“有什么景点/有哪些景点/全部景点/核心景点”，请尽量完整列出资料中能确认的全部景点。"
            "如果当前上下文已经限定为某个景区，只回答该景区，不要混入其他景区内容。"
        )

        user_prompt = (
            f"用户问题:\n{question}\n\n"
            f"检索到的资料:\n{context_text or '没有检索到资料'}\n\n"
            "请基于以上资料回答。"
            "如果问题是在问“有什么景点/有哪些景点/推荐哪些景点”，请尽量完整列出资料中能确认的景点。"
            "优先输出清晰列表，并补充每个景点的简短特点。"
            "如果资料里包含多个景区，只保留和当前问题对应景区的内容。"
            "在答案末尾用“参考片段: 1,2”这种格式标注你使用了哪些片段。"
        )

        response = llm.chat(
            [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt),
            ]
        )

        return RagAnswer(
            question=question,
            answer=response.content.strip(),
            contexts=contexts,
            model=response.model,
        )

    # =========================
    # 统计 / 预览
    # =========================
    def count(self) -> int:
        return self.guide_store.count() + self.structured_store.count()

    def preview(self, limit: int = 5) -> dict:
        return {
            "guide": self.guide_store.get(limit=limit, include=["documents", "metadatas"]),
            "structured": self.structured_store.get(limit=limit, include=["documents", "metadatas"]),
        }

    def collection_counts(self) -> dict:
        return {
            "guide": self.guide_store.count(),
            "structured": self.structured_store.count(),
            "total": self.count(),
        }

    # =========================
    # 内部辅助
    # =========================
    def _build_context_from_results(self, results: List[RetrievalResult]) -> str:
        blocks = []
        for index, result in enumerate(results, start=1):
            file_name = result.metadata.get("file_name") or result.metadata.get("source", "unknown")
            blocks.append(
                "\n".join(
                    [
                        f"[资料片段 {index}]",
                        f"来源: {file_name}",
                        f"相关度: {result.score:.4f}",
                        f"内容: {result.text}",
                    ]
                )
            )
        return "\n\n".join(blocks)

    def _build_where_for_scene(
        self,
        scene_context: Optional[SceneContext],
        chunk_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        where: Dict[str, Any] = {}

        if chunk_type:
            where["chunk_type"] = chunk_type

        if scene_context is None:
            return where

        scope_mode = getattr(scene_context, "scope_mode", "current_only")
        scenic_id = getattr(scene_context, "scenic_id", None)
        destination_id = getattr(scene_context, "destination_id", None)

        is_structured_spot = chunk_type == "structured_spot"

        # 关键修复：
        # 对结构化 spot，不在 where 层按 scenic_id 过滤，
        # 因为混合总表里 spot 级归属要靠 metadata["景区名称"] 判定。
        if is_structured_spot:
            if scope_mode != "current_only" and destination_id:
                where["destination_id"] = destination_id
            return where

        # guide 等普通文档仍按 scene id 过滤
        if scope_mode == "current_only":
            if scenic_id:
                where["scenic_id"] = scenic_id
            elif destination_id:
                where["destination_id"] = destination_id
            return where

        if destination_id:
            where["destination_id"] = destination_id

        return where

    def _matches_scene_context(
        self,
        metadata: Dict[str, Any],
        scene_context: Optional[SceneContext],
        is_structured: bool = False,
    ) -> bool:
        if scene_context is None:
            return True

        scope_mode = getattr(scene_context, "scope_mode", "current_only")
        scenic_id = getattr(scene_context, "scenic_id", None)
        destination_id = getattr(scene_context, "destination_id", None)
        scenic_name = getattr(scene_context, "scenic_name", None)
        destination_name = getattr(scene_context, "destination_name", None)

        if is_structured:
            target_scene_name = self._normalize_scenic_name(
                scenic_name or destination_name
            )
            current_scene_name = self._normalize_scenic_name(
                metadata.get("景区名称") or metadata.get("scenic_name")
            )

            if scope_mode == "current_only":
                if target_scene_name:
                    return current_scene_name == target_scene_name
                return True

            # 非 current_only 模式允许 destination 级
            if destination_id:
                return metadata.get("destination_id") == destination_id
            return True

        # guide 等普通文档继续按 id 过滤
        if scope_mode == "current_only":
            if scenic_id:
                return metadata.get("scenic_id") == scenic_id
            if destination_id:
                return metadata.get("destination_id") == destination_id
            return True

        if destination_id:
            return metadata.get("destination_id") == destination_id

        return True

    def _build_spot_summary(self, metadata: Dict[str, Any], raw_text: str) -> str:
        scenic_name = metadata.get("景区名称") or metadata.get("scenic_name") or "当前景区"
        spot_name = metadata.get("景点名称") or metadata.get("spot_name") or "未命名景点"
        spot_id = metadata.get("景点ID") or metadata.get("spot_id") or ""
        location = metadata.get("具体位置") or "未标注"
        core = metadata.get("核心功能") or "未标注"
        highlights = metadata.get("游玩亮点") or ""
        open_info = metadata.get("演艺/开放信息") or ""

        parts = [
            f"景区: {scenic_name}",
            f"景点: {spot_name}",
        ]
        if spot_id:
            parts.append(f"景点ID: {spot_id}")
        parts.append(f"位置: {location}")
        parts.append(f"特点: {core}")
        if highlights:
            parts.append(f"亮点: {highlights}")
        if open_info:
            parts.append(f"开放信息: {open_info}")

        return "\n".join(parts)

    def _spot_sort_key(self, metadata: Dict[str, Any]) -> tuple:
        scenic_name = self._normalize_scenic_name(
            metadata.get("景区名称") or metadata.get("scenic_name") or ""
        ) or ""
        chunk_index = metadata.get("chunk_index", 10**9)
        spot_id = metadata.get("景点ID") or metadata.get("spot_id") or ""
        spot_name = metadata.get("景点名称") or metadata.get("spot_name") or ""
        return (scenic_name, chunk_index, spot_id, spot_name)

    @staticmethod
    def _is_full_spot_list_query(query: str) -> bool:
        keywords = [
            "有什么景点",
            "有哪些景点",
            "景点有哪些",
            "全部景点",
            "所有景点",
            "核心景点",
            "景点都有哪些",
        ]
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _prefer_structured(query: str) -> bool:
        keywords = ["景点", "有哪些", "有什么", "推荐", "项目", "打卡", "看点", "路线"]
        return any(keyword in query for keyword in keywords)

    @staticmethod
    def _is_structured_doc(document) -> bool:
        file_name = str(document.metadata.get("file_name", ""))
        file_path = str(document.metadata.get("file_path", ""))
        doc_type = str(document.metadata.get("doc_type", ""))
        if doc_type == "structured_spots":
            return True
        return "结构化" in file_name or "结构化" in file_path

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

import types

from knowledge.service import RagKnowledgeService
from knowledge.scene_context import SceneContext


class FakeStructuredStore:
    def __init__(self, documents, metadatas):
        self._documents = documents
        self._metadatas = metadatas

    def get_all_by_filter(self, where=None, include=None):
        return {
            "documents": self._documents,
            "metadatas": self._metadatas,
        }


def build_service_with_fake_store():
    service = RagKnowledgeService.__new__(RagKnowledgeService)

    documents = [
        "LS-001 raw",
        "LS-011 raw",
        "NH-001 raw",
        "NH-005 raw",
    ]
    metadatas = [
        {
            "chunk_type": "structured_spot",
            "景区名称": "灵山胜境",
            "景点名称": "灵山大照壁",
            "景点ID": "LS-001",
            "具体位置": "景区入口处",
            "核心功能": "景区标志性门户",
            "chunk_index": 0,
        },
        {
            "chunk_type": "structured_spot",
            "景区名称": "灵山胜境",
            "景点名称": "灵山大佛",
            "景点ID": "LS-011",
            "具体位置": "祥符禅寺北侧",
            "核心功能": "核心地标",
            "chunk_index": 10,
        },
        {
            "chunk_type": "structured_spot",
            "景区名称": "拈花湾禅意小镇",
            "景点名称": "拈花广场",
            "景点ID": "NH-001",
            "具体位置": "小镇入口核心区域",
            "核心功能": "门户与集散中心",
            "chunk_index": 20,
        },
        {
            "chunk_type": "structured_spot",
            "景区名称": "拈花湾禅意小镇",
            "景点名称": "五灯湖",
            "景点ID": "NH-005",
            "具体位置": "小镇南侧",
            "核心功能": "水景与夜间演艺",
            "chunk_index": 24,
        },
    ]

    service.structured_store = FakeStructuredStore(documents, metadatas)
    return service


def test_list_spots_only_returns_lingshan_for_lingshan_scene():
    service = build_service_with_fake_store()

    scene = SceneContext(
        destination_id="lingshan_group",
        destination_name="灵山胜境",
        scenic_id="lingshan_core",
        scenic_name="灵山胜境",
        scope_mode="current_only",
    )

    results = service.list_spots(scene_context=scene, limit=None)

    names = [item.metadata.get("景点名称") for item in results]
    scenic_names = [item.metadata.get("景区名称") for item in results]

    assert "灵山大照壁" in names
    assert "灵山大佛" in names
    assert "拈花广场" not in names
    assert "五灯湖" not in names
    assert set(scenic_names) == {"灵山胜境"}


def test_list_spots_only_returns_nianhuawan_for_nianhuawan_scene():
    service = build_service_with_fake_store()

    scene = SceneContext(
        destination_id="lingshan_group",
        destination_name="灵山胜境",
        scenic_id="nianhuawan_core",
        scenic_name="拈花湾禅意小镇",
        scope_mode="current_only",
    )

    results = service.list_spots(scene_context=scene, limit=None)

    names = [item.metadata.get("景点名称") for item in results]
    scenic_names = [item.metadata.get("景区名称") for item in results]

    assert "拈花广场" in names
    assert "五灯湖" in names
    assert "灵山大照壁" not in names
    assert "灵山大佛" not in names
    assert set(scenic_names) == {"拈花湾禅意小镇"}


def test_search_full_spot_list_routes_to_list_spots_without_cross_scene():
    service = build_service_with_fake_store()

    scene = SceneContext(
        destination_id="lingshan_group",
        destination_name="灵山胜境",
        scenic_id="lingshan_core",
        scenic_name="灵山胜境",
        scope_mode="current_only",
    )

    results = service.search(
        query="灵山胜境有什么景点",
        scene_context=scene,
        top_k=20,
    )

    names = [item.metadata.get("景点名称") for item in results]

    assert "灵山大照壁" in names
    assert "灵山大佛" in names
    assert "拈花广场" not in names
    assert "五灯湖" not in names

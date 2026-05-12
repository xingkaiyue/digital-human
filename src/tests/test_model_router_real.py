import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

print(f"PROJECT_ROOT = {PROJECT_ROOT}")
print(f"SRC_ROOT = {SRC_ROOT}")
print(f"sys.path[0] = {sys.path[0]}")

from config import get_settings
from knowledge import RagKnowledgeService
from modules.fake_route_backend_client import FakeRouteBackendClient
from modules.model_router import ModelRouter

# 你项目里如果这个 import 不通，就改成 from llm.factory import build_llm_client
from llm.factory import build_llm_client


def pretty_print(title: str, data: dict) -> None:
    print("=" * 80)
    print(f"QUERY: {title}")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> None:
    settings = get_settings()

    # 真实知识库
    knowledge_service = RagKnowledgeService(settings=settings)

    # 真实 LLM 客户端
    llm_client = build_llm_client(settings)

    # 先用假的 route backend，后面你接后端接口时再替换
    route_backend_client = FakeRouteBackendClient()

    router = ModelRouter(
        llm_aggregator=llm_client,
        vector_retriever=None,
        tencent_map_client=None,
        xunfei_tts=None,
        knowledge_service=knowledge_service,
        route_backend_client=route_backend_client,
    )

    lingshan_scene = {
        "destination_id": "lingshan_group",
        "destination_name": "灵山大景区",
        "scenic_id": "lingshan_core",
        "scenic_name": "灵山胜境",
        "scope_mode": "current_only",
    }

    nianhuawan_scene = {
        "destination_id": "lingshan_group",
        "destination_name": "灵山大景区",
        "scenic_id": "nianhuawan",
        "scenic_name": "拈花湾禅意小镇",
        "scope_mode": "current_only",
    }

    family_user = {
        "travel_type": "family",
        "with_children": True,
        "budget_level": "medium",
        "pace_preference": "relaxed",
    }

    test_cases = [
        ("你好导游", lingshan_scene, {}),
        ("灵山胜境有什么景点", lingshan_scene, {}),
        ("九龙灌浴是什么", lingshan_scene, {}),
        ("适合亲子的游玩路线", lingshan_scene, family_user),
        ("从南门到梵宫怎么走", lingshan_scene, {}),
        ("拈花湾有什么景点", nianhuawan_scene, {}),
        ("谢谢你", lingshan_scene, {}),
    ]

    for query, scene_context, user_profile in test_cases:
        result = router.handle(
            query=query,
            scene_context=scene_context,
            user_profile=user_profile,
        )
        pretty_print(query, result)


if __name__ == "__main__":
    main()

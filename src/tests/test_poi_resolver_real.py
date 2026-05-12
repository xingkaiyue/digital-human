import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from config import get_settings
from knowledge import RagKnowledgeService
from knowledge.scene_context import SceneContext
from modules.poi_resolver import POIResolver


def main():
    settings = get_settings()
    knowledge_service = RagKnowledgeService(settings=settings)
    resolver = POIResolver(knowledge_service=knowledge_service, debug=True)

    scene_context = SceneContext(
        destination_id="lingshan_group",
        destination_name="灵山大景区",
        scenic_id="lingshan_core",
        scenic_name="灵山胜境",
        scope_mode="current_only",
    )

    queries = [
        "梵宫",
        "大佛",
        "九龙灌浴",
        "博览馆",
        "祥符禅寺",
    ]

    for query in queries:
        result = resolver.resolve(query_name=query, scene_context=scene_context, top_k=3)
        print("=" * 80)
        print("QUERY:", query)
        for item in result:
            print(
                {
                    "name": item.name,
                    "score": item.score,
                    "scenic_name": item.scenic_name,
                    "location": item.location,
                }
            )


if __name__ == "__main__":
    main()

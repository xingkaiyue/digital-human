import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

print("PROJECT_ROOT =", PROJECT_ROOT)
print("SRC_ROOT =", SRC_ROOT)
print("sys.path[0] =", sys.path[0])

from config import get_settings
from knowledge import RagKnowledgeService
from knowledge.scene_context import SceneContext
from llm.openai_compatible import OpenAICompatibleClient
from modules.model_router import ModelRouter
from modules.router_adapters import KnowledgeRetrieverAdapter, LLMAggregatorAdapter


class DummyMapClient:
    def plan_route(self, start_name, end_name, scenic_name=None, mode="walking"):
        return {
            "start_name": start_name,
            "end_name": end_name,
            "distance_meters": 1000,
            "duration_minutes": 15,
            "steps": [
                {"instruction": f"从{start_name}出发，沿景区主路直行。"},
                {"instruction": f"按照指引继续前往{end_name}。"},
            ],
            "provider": "dummy_map",
        }


class DummyTTS:
    def synthesize(self, text, output_path, voice="xiaoyan"):
        return None


def build_real_llm_client(settings):
    return OpenAICompatibleClient(
        provider=getattr(settings, "llm_provider", "deepseek"),
        model=getattr(settings, "llm_model", "deepseek-chat"),
        api_key=getattr(settings, "llm_api_key", ""),
        base_url=getattr(settings, "llm_base_url", ""),
        timeout_seconds=getattr(settings, "llm_timeout_seconds", 60),
        temperature=getattr(settings, "llm_temperature", 0.2),
        max_tokens=getattr(settings, "llm_max_tokens", 1024),
    )


def load_cases():
    case_path = Path(__file__).resolve().parents[1] / "fixtures" / "regression_cases.json"
    with case_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main():
    settings = get_settings()
    knowledge_service = RagKnowledgeService(settings=settings)
    retriever_adapter = KnowledgeRetrieverAdapter(knowledge_service)

    llm_client = build_real_llm_client(settings)
    llm_adapter = LLMAggregatorAdapter(llm_client)

    router = ModelRouter(
        llm_aggregator=llm_adapter,
        vector_retriever=retriever_adapter,
        tencent_map_client=DummyMapClient(),
        xunfei_tts=DummyTTS(),
        auto_tts_for_all=False,
    )

    cases = load_cases()
    failed = []

    for case in cases:
        scene_context = SceneContext(**case["scene_context"])
        result = router.handle(
            query=case["query"],
            scene_context=scene_context,
            user_profile={},
        )

        answer_text = result.get("answer_text", "")
        ok = True

        if result.get("type") != case["expected_type"]:
            ok = False
            failed.append(
                f"{case['name']}: type 错误，实际={result.get('type')} 期望={case['expected_type']}"
            )

        for keyword in case.get("must_contain", []):
            if keyword not in answer_text:
                ok = False
                failed.append(f"{case['name']}: 缺少关键词 {keyword}")

        for keyword in case.get("must_not_contain", []):
            if keyword in answer_text:
                ok = False
                failed.append(f"{case['name']}: 不应包含关键词 {keyword}")

        if ok:
            print(f"[PASS] {case['name']}")

    if failed:
        print("\n[FAILED]")
        for item in failed:
            print("-", item)
        raise SystemExit(1)

    print("\n全部回归测试通过。")


if __name__ == "__main__":
    main()

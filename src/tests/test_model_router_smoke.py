import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

print("PROJECT_ROOT =", PROJECT_ROOT)
print("SRC_ROOT =", SRC_ROOT)
print("sys.path[0] =", sys.path[0])

from modules.model_router import ModelRouter


class FakeLLMAggregator:
    def chat(self, messages=None, system_prompt=None, user_prompt=None):
        return {"content": "这是一个模拟的 LLM 回答。"}

    def generate(self, system_prompt=None, user_prompt=None, prompt=None):
        return {"content": "这是一个模拟的 LLM 生成结果。"}


class FakeVectorRetriever:
    def search(self, query, scene_context=None, top_k=5):
        return [
            {
                "text": f"关于“{query}”的模拟知识库片段1：九龙灌浴适合亲子体验。",
                "metadata": {
                    "file_name": "灵山胜境_历史文化个性化游玩指南.docx",
                    "source": "灵山胜境_历史文化个性化游玩指南",
                    "spot_name": "九龙灌浴",
                    "chunk_type": "guide",
                    "核心功能": "动态景观、科普与祈福功能",
                    "游玩亮点": "适合亲子体验",
                    "具体位置": "菩提大道北端",
                },
                "score": 0.92,
            },
            {
                "text": f"关于“{query}”的模拟知识库片段2：百子戏弥勒适合互动拍照。",
                "metadata": {
                    "file_name": "灵山胜境_景点结构化数据集.docx",
                    "source": "灵山胜境_景点结构化数据集",
                    "spot_name": "百子戏弥勒",
                    "景点名称": "百子戏弥勒",
                    "chunk_type": "structured_spot",
                    "核心功能": "亲子互动功能",
                    "游玩亮点": "互动拍照",
                    "具体位置": "祥符禅寺附近",
                },
                "score": 0.88,
            },
        ]


class FakeTencentMapClient:
    def plan_route(self, start_name, end_name, scenic_name=None, mode="walking"):
        return {
            "start_name": start_name,
            "end_name": end_name,
            "distance_meters": 850,
            "duration_minutes": 12,
            "steps": [
                {"instruction": f"从{start_name}出发，沿主步道直行。"},
                {"instruction": f"到达指示牌后右转，继续前往{end_name}。"},
            ],
            "provider": "fake_map",
        }


class FakeXunfeiTTS:
    def synthesize(self, text, output_path, voice="xiaoyan"):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-audio")
        return str(path)


class FakeSceneContext:
    def __init__(self):
        self.destination_id = "lingshan_group"
        self.destination_name = "灵山胜境"
        self.scenic_id = "lingshan_core"
        self.scenic_name = "灵山胜境"
        self.scope_mode = "current_only"
        self.user_location_text = "景区南门"
        self.route_mode = "walking"


def main():
    router = ModelRouter(
        llm_aggregator=FakeLLMAggregator(),
        vector_retriever=FakeVectorRetriever(),
        tencent_map_client=FakeTencentMapClient(),
        xunfei_tts=FakeXunfeiTTS(),
        auto_tts_for_all=False,
    )

    scene_context = FakeSceneContext()

    test_queries = [
        "你好导游",
        "灵山胜境有什么景点",
        "适合亲子的游玩路线推荐",
        "从南门到梵宫怎么走",
        "谢谢你",
    ]

    for q in test_queries:
        result = router.handle(q, scene_context=scene_context, user_profile={"group_type": "family"})
        print("=" * 80)
        print("QUERY:", q)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

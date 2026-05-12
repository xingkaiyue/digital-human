import json

from modules.model_router import ModelRouter


class FakeLLM:
    def chat(self, messages=None, system_prompt=None, user_prompt=None):
        raise RuntimeError("llm failed")


class FakeRetriever:
    def search(self, query, scene_context=None, top_k=5):
        return [
            {
                "text": "这是回退用的知识片段。",
                "metadata": {"source": "fake_source"},
                "score": 0.9,
            }
        ]


class BrokenMapClient:
    def plan_route(self, start_name, end_name, scenic_name=None, mode="walking"):
        raise RuntimeError("map api failed")


class BrokenTTS:
    def synthesize(self, text, output_path, voice="xiaoyan"):
        raise RuntimeError("tts failed")


class SceneContext:
    def __init__(self):
        self.destination_name = "灵山胜境"
        self.scenic_name = "灵山胜境"
        self.user_location_text = "南门"


def main():
    router = ModelRouter(
        llm_aggregator=FakeLLM(),
        vector_retriever=FakeRetriever(),
        tencent_map_client=BrokenMapClient(),
        xunfei_tts=BrokenTTS(),
        auto_tts_for_all=True,
    )

    ctx = SceneContext()

    cases = [
        "灵山胜境有什么景点",
        "从南门到梵宫怎么走",
    ]

    for q in cases:
        result = router.handle(q, scene_context=ctx)
        print("=" * 80)
        print("QUERY:", q)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

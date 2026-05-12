import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from modules.intent_parser import IntentParser


def main():
    parser = IntentParser()

    queries = [
        "你好导游",
        "灵山胜境有什么景点",
        "九龙灌浴是什么",
        "适合亲子的游玩路线",
        "从南门到梵宫怎么走",
        "谢谢你",
    ]

    for query in queries:
        result = parser.parse(query)
        print("=" * 80)
        print("QUERY:", query)
        print("intent =", result.intent)
        print("confidence =", result.confidence)
        print("slots =", result.slots)
        print("need_clarify =", result.need_clarify)
        print("reason =", result.reason)


if __name__ == "__main__":
    main()

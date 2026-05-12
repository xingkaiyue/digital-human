import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from modules.slot_extractor import SlotExtractor


def main():
    extractor = SlotExtractor()

    test_cases = [
        ("从南门到梵宫怎么走", "route"),
        ("去九龙灌浴怎么走", "route"),
        ("适合亲子的游玩路线", "recommend"),
        ("九龙灌浴是什么", "knowledge"),
        ("灵山大佛在哪里", "knowledge"),
    ]

    for query, intent in test_cases:
        result = extractor.extract(query=query, intent=intent)
        print("=" * 80)
        print("QUERY:", query)
        print("INTENT:", intent)
        print("SLOTS:", result.slots)
        print("MISSING:", result.missing_slots)
        print("DEBUG:", result.debug)


if __name__ == "__main__":
    main()

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from config import get_settings
from knowledge import RagKnowledgeService
from knowledge.scene_context import SceneContext
from services.tencent_map_client import TencentMapClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="多景区导游模型层入口",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="导入单个文档")
    ingest_parser.add_argument("file_path", help="文档路径")
    ingest_parser.add_argument("--destination-id", required=True)
    ingest_parser.add_argument("--destination-name", required=True)
    ingest_parser.add_argument("--scenic-id", default=None)
    ingest_parser.add_argument("--scenic-name", default=None)
    ingest_parser.add_argument("--doc-type", default="guide")

    search_parser = subparsers.add_parser("search", help="仅检索相似片段")
    search_parser.add_argument("query", help="用户问题")
    search_parser.add_argument("--destination-id", required=True)
    search_parser.add_argument("--destination-name", required=True)
    search_parser.add_argument("--scenic-id", default=None)
    search_parser.add_argument("--scenic-name", default=None)
    search_parser.add_argument("--scope-mode", default="current_only")
    search_parser.add_argument("--top-k", type=int, default=None)

    ask_parser = subparsers.add_parser("ask", help="执行问答")
    ask_parser.add_argument("query", help="用户问题")
    ask_parser.add_argument("--destination-id", required=True)
    ask_parser.add_argument("--destination-name", required=True)
    ask_parser.add_argument("--scenic-id", default=None)
    ask_parser.add_argument("--scenic-name", default=None)
    ask_parser.add_argument("--scope-mode", default="current_only")
    ask_parser.add_argument("--top-k", type=int, default=None)

    preview_parser = subparsers.add_parser("preview", help="查看向量库样本")
    preview_parser.add_argument("--limit", type=int, default=5)

    count_parser = subparsers.add_parser("count", help="查看当前向量数量")

    route_parser = subparsers.add_parser("route-test", help="测试腾讯路线规划")
    route_parser.add_argument("--from-lat", required=True, type=float)
    route_parser.add_argument("--from-lng", required=True, type=float)
    route_parser.add_argument("--to-lat", required=True, type=float)
    route_parser.add_argument("--to-lng", required=True, type=float)
    route_parser.add_argument("--mode", default="walk")

    return parser


def build_scene_context(args) -> SceneContext:
    return SceneContext(
        destination_id=args.destination_id,
        destination_name=args.destination_name,
        scenic_id=args.scenic_id,
        scenic_name=args.scenic_name,
        scope_mode=args.scope_mode,
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    settings = get_settings()
    map_client = TencentMapClient(settings=settings)
    service = RagKnowledgeService(settings=settings, map_client=map_client)

    if args.command == "ingest":
        chunks = service.ingest_file(
            file_path=args.file_path,
            destination_id=args.destination_id,
            destination_name=args.destination_name,
            scenic_id=args.scenic_id,
            scenic_name=args.scenic_name,
            doc_type=args.doc_type,
        )
        print(f"已导入文档: {args.file_path}")
        print(f"生成 chunk 数量: {len(chunks)}")
        print(f"当前向量统计: {json.dumps(service.collection_counts(), ensure_ascii=False)}")
        return

    if args.command == "search":
        scene_context = build_scene_context(args)
        results = service.search(args.query, scene_context=scene_context, top_k=args.top_k)
        print(f"query: {args.query}")
        print(f"命中结果: {len(results)}")
        print("-" * 60)
        for index, result in enumerate(results, start=1):
            print(f"[{index}] score={result.score:.4f} distance={result.distance:.4f}")
            print(f"metadata={json.dumps(result.metadata, ensure_ascii=False)}")
            print(f"text={result.text}")
            print("-" * 60)
        return

    if args.command == "ask":
        scene_context = build_scene_context(args)
        rag_answer = service.answer(args.query, scene_context=scene_context, top_k=args.top_k)
        print(f"model: {rag_answer.model}")
        print(f"question: {rag_answer.question}")
        print("answer:")
        print(rag_answer.answer)
        print("\nretrieved_contexts:")
        for index, item in enumerate(rag_answer.contexts, start=1):
            print(
                f"[{index}] score={item.score:.4f} "
                f"source={item.metadata.get('file_name') or item.metadata.get('source')}"
            )
            print(item.text)
            print("-" * 60)
        return

    if args.command == "preview":
        preview = service.preview(limit=args.limit)
        print(json.dumps(preview, ensure_ascii=False, indent=2, default=str))
        return

    if args.command == "count":
        print(json.dumps(service.collection_counts(), ensure_ascii=False))
        return

    if args.command == "route-test":
        result = service.route_test(
            from_lat=args.from_lat,
            from_lng=args.from_lng,
            to_lat=args.to_lat,
            to_lng=args.to_lng,
            mode=args.mode,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return

    raise ValueError(f"未知命令: {args.command}")


if __name__ == "__main__":
    main()

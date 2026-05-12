# main.py
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from extractors.file_reader import FileReader
from extractors.table_parser import TableParser
from builders.kg_builder import KnowledgeGraphBuilder

# 您的文件路径
FILE2 = r"C:\Users\34829\PycharmProjects\ai-model\src\data\灵山胜境_景点结构化数据集.docx"


def main():
    print("=" * 60)
    print("灵山胜境知识图谱构建器")
    print("=" * 60)

    # 1. 读取文件
    print("\n📁 读取Word文档...")
    text, tables = FileReader.read_file(FILE2)

    if not tables:
        print("❌ 未找到表格！")
        return

    print(f"   找到 {len(tables)} 个表格")

    # 2. 解析表格
    print("\n🔍 解析表格数据...")
    parser = TableParser()
    triplets = parser.parse_tables(tables)

    # 去重
    triplets = list(set(triplets))

    print(f"\n📊 提取结果: {len(triplets)} 条三元组")

    # 显示部分三元组
    print("\n📋 三元组示例 (前20条):")
    for i, (s, p, o) in enumerate(triplets[:20], 1):
        o_short = o[:40] + "..." if len(o) > 40 else o
        print(f"   {i:2d}. ({s}) -[{p}]-> ({o_short})")

    # 3. 构建知识图谱
    print("\n" + "=" * 60)
    print("💾 保存并构建知识图谱...")
    print("=" * 60)

    # 创建构建器
    builder = KnowledgeGraphBuilder()

    # 添加三元组
    builder.add_triplets(triplets)

    # 保存文件（使用正确的方法名）
    builder.save_triplets_to_json("output/triplets.json")
    builder.save_triplets_to_csv("output/triplets.csv")
    builder.export_cypher_script("output/kg.cypher")

    # 打印摘要
    builder.print_summary()

    # 构建到Neo4j
    if builder.handler.connect():
        builder.build(clear_first=True)
        stats = builder.get_statistics()
        print(f"\n✅ 知识图谱构建完成!")
        print(f"   节点数: {stats.get('nodes', 0)}")
        print(f"   关系数: {stats.get('relations', 0)}")
        builder.disconnect()
    else:
        print("\n⚠️ Neo4j未连接，但文件已保存到 output/ 目录")

    print("\n" + "=" * 60)
    print("🎉 完成!")
    print("=" * 60)
    print("\n🌐 访问 http://localhost:7474 查看知识图谱")
    print("   运行: MATCH (n) RETURN n LIMIT 100")


if __name__ == "__main__":
    main()
# builders/kg_builder.py
import json
import os
import re
from typing import List, Tuple, Dict, Any, Optional

# 添加项目根目录到路径
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from graph_base.handle_graph import GraphHandler
except ImportError:
    print("❌ 无法导入 GraphHandler，请检查路径")
    raise


class KnowledgeGraphBuilder:
    """知识图谱构建器 - 用于构建灵山胜境知识图谱"""

    def __init__(self):
        """初始化构建器"""
        self.handler = GraphHandler()
        self.triplets: List[Tuple[str, str, str]] = []
        print("✅ KnowledgeGraphBuilder 初始化完成")

    def add_triplet(self, subject: str, predicate: str, object_: str) -> 'KnowledgeGraphBuilder':
        """
        添加单个三元组

        Args:
            subject: 主体实体
            predicate: 关系
            object_: 客体实体

        Returns:
            self, 支持链式调用
        """
        if subject and predicate and object_:
            self.triplets.append((subject.strip(), predicate.strip(), object_.strip()))
        return self

    def add_triplets(self, triplets: List[Tuple[str, str, str]]) -> 'KnowledgeGraphBuilder':
        """
        批量添加三元组

        Args:
            triplets: 三元组列表

        Returns:
            self, 支持链式调用
        """
        for subj, pred, obj in triplets:
            self.add_triplet(subj, pred, obj)
        return self

    def get_triplets(self) -> List[Tuple[str, str, str]]:
        """获取所有三元组"""
        return self.triplets.copy()

    def get_triplet_count(self) -> int:
        """获取三元组数量"""
        return len(self.triplets)

    def clear_triplets(self) -> 'KnowledgeGraphBuilder':
        """清空三元组"""
        self.triplets = []
        return self

    def save_triplets_to_json(self, file_path: str = "output/triplets.json") -> 'KnowledgeGraphBuilder':
        """
        保存三元组到JSON文件

        Args:
            file_path: 输出文件路径

        Returns:
            self, 支持链式调用
        """
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        data = []
        for s, p, o in self.triplets:
            data.append({
                "subject": s,
                "predicate": p,
                "object": o
            })

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"✅ 三元组已保存到 {file_path}")
        return self

    def save_triplets_to_csv(self, file_path: str = "output/triplets.csv") -> 'KnowledgeGraphBuilder':
        """
        保存三元组到CSV文件

        Args:
            file_path: 输出文件路径

        Returns:
            self, 支持链式调用
        """
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        # 手动写入CSV，避免pandas依赖
        with open(file_path, 'w', encoding='utf-8-sig') as f:
            f.write("实体1,关系,实体2\n")
            for s, p, o in self.triplets:
                # 处理可能包含逗号的内容
                s_clean = s.replace(',', '，')
                p_clean = p.replace(',', '，')
                o_clean = o.replace(',', '，')
                f.write(f"{s_clean},{p_clean},{o_clean}\n")

        print(f"✅ 三元组已保存到 {file_path}")
        return self

    def export_cypher_script(self, file_path: str = "output/kg.cypher") -> 'KnowledgeGraphBuilder':
        """
        导出Cypher脚本，可直接在Neo4j Browser中运行

        Args:
            file_path: 输出文件路径

        Returns:
            self, 支持链式调用
        """
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        lines = []
        lines.append("// ============================================")
        lines.append("// 灵山胜境知识图谱构建脚本")
        lines.append("// 在Neo4j Browser中运行此脚本")
        lines.append("// ============================================")
        lines.append("")
        lines.append("// 清空数据库")
        lines.append("MATCH (n) DETACH DELETE n;")
        lines.append("")
        lines.append("// 创建约束")
        lines.append("CREATE CONSTRAINT IF NOT EXISTS FOR (s:Scene) REQUIRE s.name IS UNIQUE;")
        lines.append("")
        lines.append("// ============================================")
        lines.append("// 创建节点")
        lines.append("// ============================================")
        lines.append("")

        # 收集所有唯一节点
        nodes = set()
        for s, p, o in self.triplets:
            if s and len(s) >= 2:
                nodes.add(s)
            if o and len(o) >= 2:
                nodes.add(o)

        # 创建节点
        for node in sorted(nodes):
            if len(node) <= 100:
                # 转义单引号
                node_escaped = node.replace("'", "\\'")
                lines.append(f"MERGE (n:Entity {{name: '{node_escaped}'}});")

        lines.append("")
        lines.append("// ============================================")
        lines.append("// 创建关系")
        lines.append("// ============================================")
        lines.append("")

        # 创建关系
        for s, p, o in self.triplets:
            if s and o and len(s) >= 2 and len(o) >= 2:
                # 规范化关系名称
                rel_name = re.sub(r'[^\u4e00-\u9fa5a-zA-Z]', '_', p)
                rel_name = rel_name.upper()
                if not rel_name:
                    rel_name = "RELATED_TO"

                s_escaped = s.replace("'", "\\'")
                o_escaped = o.replace("'", "\\'")

                lines.append(f"MATCH (a {{name: '{s_escaped}'}});")
                lines.append(f"MATCH (b {{name: '{o_escaped}'}});")
                lines.append(f"MERGE (a)-[:{rel_name}]->(b);")
                lines.append("")

        lines.append("// ============================================")
        lines.append("// 验证结果")
        lines.append("// ============================================")
        lines.append("MATCH (n) RETURN count(n) as total_nodes;")
        lines.append("MATCH ()-[r]->() RETURN count(r) as total_relations;")

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        print(f"✅ Cypher脚本已导出到 {file_path}")
        return self

    def build(self, clear_first: bool = True) -> 'KnowledgeGraphBuilder':
        """
        构建Neo4j知识图谱

        Args:
            clear_first: 是否先清空数据库

        Returns:
            self, 支持链式调用
        """
        print("\n" + "=" * 50)
        print("开始构建Neo4j知识图谱")
        print("=" * 50)

        # 连接数据库
        if not self.handler.connect():
            print("❌ 数据库连接失败")
            return self

        # 清空数据库
        if clear_first:
            self.handler.clear_all()

        # 创建约束
        self.handler.create_constraints()

        # 构建图谱
        self.handler.build_from_triplets(self.triplets)

        # 获取统计信息
        stats = self.handler.get_statistics()
        print(f"\n📊 构建完成统计:")
        print(f"   - 节点数: {stats.get('nodes', 0)}")
        print(f"   - 关系数: {stats.get('relations', 0)}")

        return self

    def query_scene(self, scene_name: str) -> List[Dict[str, Any]]:
        """
        查询景点的关系网络

        Args:
            scene_name: 景点名称

        Returns:
            关系列表
        """
        results = self.handler.query_scene(scene_name)

        print(f"\n🔗 '{scene_name}' 的关系网络:")
        if results:
            for r in results:
                rel = r.get('relation', '关联')
                name = r.get('name', '未知')
                print(f"   --{rel}--> {name}")
        else:
            print("   暂无关联关系")

        return results

    def get_all_scenes(self) -> List[Dict[str, Any]]:
        """
        获取所有景点

        Returns:
            景点列表
        """
        scenes = self.handler.get_all_scenes()

        print(f"\n📋 所有景点 ({len(scenes)}个):")
        for s in scenes:
            name = s.get('name', '')
            category = s.get('category', '默认')
            print(f"   - {name} [{category}]")

        return scenes

    def get_statistics(self) -> Dict[str, int]:
        """
        获取数据库统计信息

        Returns:
            统计信息字典
        """
        return self.handler.get_statistics()

    def execute_query(self, cypher: str, params: Dict = None) -> List[Dict]:
        """
        执行自定义Cypher查询

        Args:
            cypher: Cypher查询语句
            params: 查询参数

        Returns:
            查询结果
        """
        return self.handler.query(cypher, params)

    def disconnect(self) -> 'KnowledgeGraphBuilder':
        """断开数据库连接"""
        self.handler.disconnect()
        return self

    def print_summary(self):
        """打印构建摘要"""
        print("\n" + "=" * 50)
        print("知识图谱构建摘要")
        print("=" * 50)
        print(f"三元组数量: {len(self.triplets)}")

        # 统计关系类型
        relation_types = {}
        for s, p, o in self.triplets:
            if p not in relation_types:
                relation_types[p] = 0
            relation_types[p] += 1

        print(f"\n关系类型分布:")
        for rel, count in sorted(relation_types.items(), key=lambda x: -x[1]):
            print(f"   - {rel}: {count} 条")

        # 统计实体
        entities = set()
        for s, p, o in self.triplets:
            entities.add(s)
            entities.add(o)

        print(f"\n实体数量: {len(entities)}")

        return self


# 便捷函数
def create_builder() -> KnowledgeGraphBuilder:
    """创建知识图谱构建器"""
    return KnowledgeGraphBuilder()


if __name__ == "__main__":
    # 测试代码
    print("测试 KnowledgeGraphBuilder...")
    builder = KnowledgeGraphBuilder()

    # 添加测试三元组
    builder.add_triplet("测试景点1", "位于", "测试位置1")
    builder.add_triplet("测试景点2", "高度", "100米")
    builder.add_triplet("灵山胜境", "包含", "测试景点1")

    print(f"添加了 {builder.get_triplet_count()} 条三元组")
    print(f"三元组: {builder.get_triplets()}")

    # 保存文件
    builder.save_triplets_to_json("output/test_triplets.json")
    builder.export_cypher_script("output/test_kg.cypher")

    print("\n测试完成!")
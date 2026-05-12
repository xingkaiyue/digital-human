# graph_base/handle_graph.py
import re
from typing import List, Tuple, Dict
from .graph_config import GraphConfig
from .graph_data_base import GraphDataBase


class GraphHandler(GraphDataBase):
    """Neo4j图数据库操作处理类"""

    def __init__(self):
        self.config = GraphConfig()
        self._graph = None

    def connect(self, uri: str = None, username: str = None, password: str = None):
        """连接Neo4j数据库"""
        try:
            from py2neo import Graph
            neo4j_config = self.config.get_neo4j_config()
            uri = uri or neo4j_config["uri"]
            username = username or neo4j_config["username"]
            password = password or neo4j_config["password"]

            self._graph = Graph(uri, auth=(username, password))
            self._graph.run("RETURN 1")
            print(f"✅ Neo4j连接成功: {uri}")
            return True
        except Exception as e:
            print(f"❌ Neo4j连接失败: {e}")
            return False

    def disconnect(self):
        self._graph = None
        print("✅ 已断开Neo4j连接")

    def query(self, cypher: str, params: Dict = None) -> List[Dict]:
        """执行查询"""
        if not self._graph:
            return []
        try:
            result = self._graph.run(cypher, params or {})
            return result.data()
        except Exception as e:
            print(f"查询失败: {e}")
            return []

    def clear_all(self):
        """清空所有数据"""
        if not self._graph:
            return False
        try:
            self.query("MATCH (n) DETACH DELETE n")
            print("✅ 数据库已清空")
            return True
        except Exception as e:
            print(f"清空失败: {e}")
            return False

    def create_constraints(self):
        """创建约束"""
        if not self._graph:
            return False

        self.query("DROP INDEX scene_name_index IF EXISTS")
        self.query("DROP CONSTRAINT scene_name_unique IF EXISTS")

        try:
            self.query("CREATE CONSTRAINT scene_name_unique FOR (s:Scene) REQUIRE s.name IS UNIQUE")
            print("✅ 约束创建成功")
        except Exception as e:
            if "already exists" in str(e):
                print("✅ 约束已存在")
            else:
                print(f"约束创建跳过: {e}")

        return True

    def get_statistics(self) -> Dict:
        """获取统计信息"""
        if not self._graph:
            return {}
        try:
            node_count = self.query("MATCH (n) RETURN count(n) as c")[0]['c']
            rel_count = self.query("MATCH ()-[r]->() RETURN count(r) as c")[0]['c']
            return {"nodes": node_count, "relations": rel_count}
        except:
            return {"nodes": 0, "relations": 0}

    def _clean_name(self, name: str) -> str:
        """清理实体名称"""
        if not name:
            return ""
        cleaned = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', name)
        cleaned = cleaned.strip()
        if not cleaned or len(cleaned) < 2:
            chinese_only = re.sub(r'[^\u4e00-\u9fa5]', '', name)
            return chinese_only[:20] if chinese_only else "未知实体"
        return cleaned[:30]

    def _get_category(self, name: str) -> str:
        """根据景点名称判断类别"""
        category_map = {
            "佛像": ["大佛", "弥勒", "佛手", "佛足"],
            "寺庙": ["禅寺", "祥符"],
            "建筑": ["梵宫", "坛城", "照壁", "门", "桥", "柱"],
            "景观": ["灌浴", "浮雕", "花海", "湖", "谷", "大道"],
            "广场": ["广场"],
            "塔": ["塔"],
            "小镇": ["小镇"],
            "商业街": ["花街"],
            "花海": ["花海"],
            "水景": ["湖", "水景"],
            "禅堂": ["堂", "斋", "精舍"],
        }
        for category, keywords in category_map.items():
            for kw in keywords:
                if kw in name:
                    return category
        return "默认"

    def _get_label(self, name: str) -> str:
        """确定节点标签"""
        scene_keywords = ["大佛", "梵宫", "坛城", "塔", "禅寺", "广场", "大道",
                          "灌浴", "照壁", "门", "桥", "柱", "花海", "湖", "谷",
                          "堂", "斋", "精舍", "胜境", "小镇", "花街"]
        for kw in scene_keywords:
            if kw in name:
                return "Scene"
        return "Entity"

    def _normalize_relation(self, relation: str) -> str:
        """规范化关系名称"""
        cleaned = re.sub(r'[^\u4e00-\u9fa5a-zA-Z]', '_', relation)
        if cleaned.strip('_') == '':
            return "RELATED_TO"
        return cleaned.upper()

    def build_from_triplets(self, triplets: List[Tuple[str, str, str]]):
        """从三元组构建图谱（节点带颜色）"""
        if not self._graph:
            print("请先连接数据库")
            return 0

        count = 0

        # 颜色映射（16进制颜色码）
        color_map = {
            "佛像": "#FF6B6B",
            "寺庙": "#4ECDC4",
            "建筑": "#45B7D1",
            "景观": "#96CEB4",
            "广场": "#FFEAA7",
            "塔": "#DDA0DD",
            "小镇": "#F39C12",
            "商业街": "#E74C3C",
            "花海": "#2ECC71",
            "水景": "#3498DB",
            "禅堂": "#9B59B6",
            "默认": "#95A5A6"
        }

        # 创建所有景点节点（带颜色属性）
        scenes = set()
        for subj, pred, obj in triplets:
            scenes.add(subj)
            scenes.add(obj)

        print(f"📦 正在创建 {len(scenes)} 个节点...")

        for scene in scenes:
            clean_scene = self._clean_name(scene)
            if clean_scene and len(clean_scene) >= 2:
                category = self._get_category(clean_scene)
                color = color_map.get(category, color_map["默认"])
                label = self._get_label(clean_scene)

                try:
                    # 创建节点并设置颜色属性
                    self.query(f"""
                        MERGE (s:{label} {{name: $name}})
                        SET s.category = $category,
                            s.color = $color
                        RETURN s
                    """, {"name": clean_scene, "category": category, "color": color})
                    print(f"   ✅ 创建节点: {clean_scene} [{category}] 颜色: {color}")
                except Exception as e:
                    print(f"   ❌ 创建失败: {clean_scene} - {e}")

        # 创建关系
        print(f"🔗 正在创建关系...")
        for subj, pred, obj in triplets:
            subj_clean = self._clean_name(subj)
            pred_clean = self._normalize_relation(pred)
            obj_clean = self._clean_name(obj)

            if not subj_clean or not obj_clean:
                continue
            if len(subj_clean) < 2 or len(obj_clean) < 2:
                continue

            try:
                self.query(f"""
                    MATCH (s {{name: $subj}})
                    MATCH (o {{name: $obj}})
                    MERGE (s)-[:{pred_clean}]->(o)
                """, {"subj": subj_clean, "obj": obj_clean})
                count += 1
            except:
                pass

        print(f"✅ 创建了 {count} 条关系")

        # 显示各类别统计
        category_stats = self.query("""
            MATCH (s:Scene)
            RETURN s.category as category, count(s) as count
            ORDER BY count DESC
        """)

        print("\n📊 节点类别统计:")
        for stat in category_stats:
            print(f"   {stat['category']}: {stat['count']} 个节点")

        return count

    def get_all_scenes(self) -> List[Dict]:
        """获取所有景点"""
        return self.query(
            "MATCH (s:Scene) RETURN s.name as name, s.category as category, s.color as color ORDER BY s.name")

    def query_scene(self, name: str) -> List[Dict]:
        """查询景点关系"""
        name_clean = self._clean_name(name)
        return self.query("""
            MATCH (s {name: $name})-[r]-(related)
            RETURN related.name as name, related.category as category, type(r) as relation
            LIMIT 30
        """, {"name": name_clean})
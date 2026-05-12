# extractors/scene_extractor.py
from typing import List, Tuple
from .base_extractor import BaseExtractor
from graph_base.graph_config import GraphConfig


class SceneExtractor(BaseExtractor):
    """景点信息提取器"""

    def __init__(self):
        super().__init__()
        self.config = GraphConfig()

    def extract(self, data: str = None) -> List[Tuple[str, str, str]]:
        """从配置中提取景点数据"""
        ling_shan_data = self.config.get_ling_shan_data()
        scenes = ling_shan_data.get('scenes', [])

        for scene in scenes:
            name = scene.get('name')
            if not name:
                continue

            # 提取属性
            for key, value in scene.items():
                if key == 'properties':
                    for prop_key, prop_value in value.items():
                        self.add_triplet(name, prop_key, prop_value)
                elif key not in ['name', 'id'] and value:
                    self.add_triplet(name, key, value)

            # 添加景区包含关系
            self.add_triplet('灵山胜境', '包含', name)

        print(f"📊 SceneExtractor 提取了 {len(self.triplets)} 条三元组")
        return self.triplets
# extractors/smart_extractor.py
import re
from typing import List, Tuple
from .base_extractor import BaseExtractor


class SmartExtractor(BaseExtractor):
    """智能提取器 - 从文本中提取三元组"""

    def extract(self, text: str) -> List[Tuple[str, str, str]]:
        """从文本中提取三元组"""
        self.triplets = []

        # 预定义的核心景点
        core_scenes = ["灵山大佛", "灵山梵宫", "五印坛城", "曼飞龙塔", "九龙灌浴", "祥符禅寺"]

        # 添加包含关系
        for scene in core_scenes:
            self.add_triplet("灵山胜境", "包含", scene)

        # 提取位置关系
        location_patterns = [
            (r'([^，,\n。]{2,10}?)位于([^，,\n。]{2,20}?)',),
        ]

        # 提取数值属性
        height_match = re.findall(r'([^，,\n。]{2,10}?)高(\d+(?:\.\d+)?)米', text)
        for name, height in height_match:
            if any(s in name for s in core_scenes):
                self.add_triplet(name, "高度", f"{height}米")

        return self.triplets
# extractors/relation_extractor.py
from typing import List, Tuple
from .base_extractor import BaseExtractor
from graph_base.graph_config import GraphConfig


class RelationExtractor(BaseExtractor):
    """关系提取器"""

    def __init__(self):
        super().__init__()
        self.config = GraphConfig()

    def extract(self, data: str = None) -> List[Tuple[str, str, str]]:
        """从配置中提取关系数据"""
        ling_shan_data = self.config.get_ling_shan_data()
        relations = ling_shan_data.get('relations', [])

        for rel in relations:
            if len(rel) == 3:
                self.add_triplet(rel[0], rel[1], rel[2])

        # 添加更多预定义关系
        predefined_relations = [
            ("灵山大佛", "高度", "88米"),
            ("灵山大佛", "总高", "101.5米"),
            ("灵山大佛", "用铜量", "725吨"),
            ("灵山大佛", "右手手印", "施无畏印"),
            ("灵山大佛", "左手手印", "施与愿印"),
            ("灵山梵宫", "建筑面积", "7.2万平方米"),
            ("灵山梵宫", "造价", "18亿元"),
            ("灵山梵宫", "别称", "佛教艺术的卢浮宫"),
            ("五印坛城", "建筑风格", "藏传佛教"),
            ("五印坛城", "别称", "小布达拉宫"),
            ("曼飞龙塔", "建筑风格", "南传佛教"),
            ("九龙灌浴", "高度", "27.5米"),
            ("九龙灌浴", "重量", "260吨"),
            ("九龙灌浴", "表演内容", "花开见佛"),
            ("祥符禅寺", "始建于", "唐代贞观年间"),
            ("祥符禅寺", "创建者", "玄奘法师"),
            ("祥符禅寺", "历史遗存", "千年银杏"),
            ("菩提大道", "长度", "250米"),
            ("五智门", "高度", "16.8米"),
            ("阿育王柱", "高度", "16.9米"),
            ("天下第一掌", "高度", "11.7米"),
            ("天下第一掌", "宽度", "5.5米"),
            ("灵山梵宫", "融合艺术", "东阳木雕"),
            ("灵山梵宫", "融合艺术", "敦煌壁画"),
            ("灵山梵宫", "融合艺术", "扬州漆器"),
        ]

        for subj, pred, obj in predefined_relations:
            self.add_triplet(subj, pred, obj)

        print(f"📊 RelationExtractor 提取了 {len(self.triplets)} 条三元组")
        return self.triplets
# extractors/base_extractor.py
from typing import List, Tuple
from abc import ABC, abstractmethod


class BaseExtractor(ABC):
    """提取器基类"""

    def __init__(self):
        self.triplets: List[Tuple[str, str, str]] = []

    @abstractmethod
    def extract(self, data=None) -> List[Tuple[str, str, str]]:
        """提取三元组 - 子类必须实现"""
        pass

    def add_triplet(self, subj: str, pred: str, obj: str):
        """添加三元组"""
        # 清理数据
        subj = subj.strip()
        pred = pred.strip()
        obj = obj.strip()

        # 过滤无效数据
        if not subj or not pred or not obj:
            return
        if len(subj) < 2 or len(obj) < 2:
            return

        # 过滤无意义的词
        invalid_words = ["让游客", "有的", "感受", "完美", "象征", "矗立", "隐藏", "石桥", "寓意", "位于"]
        if subj in invalid_words or obj in invalid_words:
            return

        triplet = (subj, pred, obj)
        if triplet not in self.triplets:
            self.triplets.append(triplet)

    def get_triplets(self) -> List[Tuple]:
        return self.triplets

    def clear(self):
        self.triplets = []
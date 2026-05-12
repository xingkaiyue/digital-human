# graph_base/graph_data_base.py
from typing import List, Tuple, Dict, Any, Optional
from abc import ABC, abstractmethod


class GraphDataBase(ABC):
    """图数据库基类"""

    @abstractmethod
    def connect(self, **kwargs):
        """连接数据库"""
        pass

    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass

    @abstractmethod
    def clear_all(self):
        """清空所有数据"""
        pass

    @abstractmethod
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        pass

    @abstractmethod
    def query(self, cypher: str, params: Dict = None) -> List[Dict]:
        """执行查询"""
        pass
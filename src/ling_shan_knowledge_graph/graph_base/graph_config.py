# graph_base/graph_config.py
import os
import yaml
from typing import Dict


class GraphConfig:
    """图谱配置管理类"""

    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self._load_config()

    def _load_config(self):
        """加载配置文件"""
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'models.yaml')

        with open(config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)

    def get(self, key: str, default=None):
        """获取配置"""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def get_neo4j_config(self) -> Dict:
        """获取Neo4j配置"""
        return {
            "uri": self.get("NEO4J_CONFIG.uri", "bolt://localhost:7687"),
            "username": self.get("NEO4J_CONFIG.username", "neo4j"),
            "password": self.get("NEO4J_CONFIG.password", "neo4j"),
            "database": self.get("NEO4J_CONFIG.database", "neo4j")
        }
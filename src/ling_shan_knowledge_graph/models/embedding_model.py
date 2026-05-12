# models/embedding_model.py
from typing import List, Optional
import os


class EmbeddingModel:
    """Embedding模型管理类"""

    def __init__(self, provider: str = "local"):
        self.provider = provider
        self._client = None
        self._dimension = 768

    def init_client(self):
        """初始化客户端"""
        if self.provider == "siliconflow":
            self._init_siliconflow()
        elif self.provider == "zhipu":
            self._init_zhipu()
        else:
            self._init_local()

    def _init_siliconflow(self):
        """初始化SiliconFlow"""
        try:
            from openai import OpenAI
            api_key = os.environ.get("SILICONFLOW_API_KEY")
            if api_key:
                self._client = OpenAI(
                    api_key=api_key,
                    base_url="https://api.siliconflow.cn/v1"
                )
                self._dimension = 1024
                print("✅ SiliconFlow Embedding模型已初始化")
            else:
                print("⚠️ SILICONFLOW_API_KEY未设置，使用本地模型")
                self._init_local()
        except ImportError:
            self._init_local()

    def _init_zhipu(self):
        """初始化智谱"""
        try:
            from zhipuai import ZhipuAI
            api_key = os.environ.get("ZHIPUAI_API_KEY")
            if api_key:
                self._client = ZhipuAI(api_key=api_key)
                self._dimension = 1024
                print("✅ 智谱Embedding模型已初始化")
            else:
                self._init_local()
        except ImportError:
            self._init_local()

    def _init_local(self):
        """初始化本地模型"""
        try:
            from sentence_transformers import SentenceTransformer
            self._client = SentenceTransformer('BAAI/bge-small-zh-v1.5')
            self._dimension = 512
            print("✅ 本地Embedding模型已初始化")
        except ImportError:
            print("⚠️ sentence-transformers未安装，Embedding功能不可用")
            self._client = None

    def embed(self, text: str) -> Optional[List[float]]:
        """生成文本向量"""
        if not self._client:
            return None

        try:
            if self.provider in ["siliconflow", "zhipu"]:
                response = self._client.embeddings.create(
                    model="BAAI/bge-m3",
                    input=text
                )
                return response.data[0].embedding
            else:
                return self._client.encode(text).tolist()
        except Exception as e:
            print(f"Embedding失败: {e}")
            return None

    @property
    def dimension(self) -> int:
        return self._dimension
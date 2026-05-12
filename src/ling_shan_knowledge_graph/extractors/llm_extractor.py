# extractors/llm_extractor.py
import json
import re
from typing import List, Tuple
from .base_extractor import BaseExtractor


class LLMExtractor(BaseExtractor):
    """使用大模型提取三元组（需要API Key）"""

    def __init__(self, api_key: str = None, provider: str = "deepseek"):
        super().__init__()
        self.client = None
        self.provider = provider
        self._init_client(api_key)

    def _init_client(self, api_key):
        try:
            from openai import OpenAI

            if self.provider == "deepseek":
                self.client = OpenAI(
                    api_key=api_key or "YOUR_DEEPSEEK_KEY",
                    base_url="https://api.deepseek.com/v1"
                )
                self.model = "deepseek-chat"
            elif self.provider == "siliconflow":
                self.client = OpenAI(
                    api_key=api_key or "YOUR_SILICONFLOW_KEY",
                    base_url="https://api.siliconflow.cn/v1"
                )
                self.model = "Qwen/Qwen2.5-7B-Instruct"
        except ImportError:
            print("⚠️ openai未安装，LLM提取器不可用")

    def extract(self, text: str) -> List[Tuple[str, str, str]]:
        """使用LLM提取三元组"""
        if not self.client:
            print("⚠️ LLM未配置，请使用SmartExtractor")
            return []

        prompt = f"""
        从以下文本中提取所有知识三元组，格式为(实体1, 关系, 实体2)。
        只输出JSON数组，不要有其他文字。

        文本：
        {text[:3000]}

        示例输出：
        [
            ["灵山大佛", "高度", "88米"],
            ["灵山梵宫", "位于", "香水海之畔"]
        ]
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            result = response.choices[0].message.content
            json_match = re.search(r'\[\[.*?\]\]', result, re.DOTALL)
            if json_match:
                triplets = eval(json_match.group())
                return [tuple(t) for t in triplets]
        except Exception as e:
            print(f"LLM提取失败: {e}")

        return []
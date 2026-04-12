# src/knowledge/loader/structured_loader.py
from knowledge.chunker.schema import Document


class StructuredLoader:
    def load(self, file_path: str) -> Document:
        # 示例占位，后续接 CSV / Excel / JSON
        raise NotImplementedError("结构化 loader 暂未实现")
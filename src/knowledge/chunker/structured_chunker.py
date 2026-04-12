from typing import List
from docx import Document as DocxDocument

from .base_chunker import BaseChunker
from .schema import Document, DocumentChunk


class StructuredDocxChunker(BaseChunker):
    """
    docx 表格 chunker
    一行 = 一个 chunk（工程级）
    """

    def split(self, document: Document) -> List[DocumentChunk]:
        file_path = document.metadata.get("file_path")
        if not file_path:
            raise ValueError("StructuredDocxChunker 需要 metadata['file_path']")

        doc = DocxDocument(file_path)

        chunks: List[DocumentChunk] = []
        chunk_id = 0

        for table_index, table in enumerate(doc.tables):
            if len(table.rows) <= 1:
                continue  # 没数据

            # 表头
            headers = [cell.text.strip() for cell in table.rows[0].cells]

            for row_index, row in enumerate(table.rows[1:], start=1):
                cells = [cell.text.strip() for cell in row.cells]

                if not any(cells):
                    continue

                row_data = {
                    headers[i] if i < len(headers) else f"字段{i}": cells[i]
                    for i in range(len(cells))
                }

                # 核心：结构化转自然语言
                text = "；".join(
                    f"{k}：{v}" for k, v in row_data.items() if v
                )

                chunks.append(
                    DocumentChunk(
                        chunk_id=chunk_id,
                        text=text,
                        metadata={
                            "source": document.metadata.get("source"),
                            "file_path": file_path,
                            "table_index": table_index,
                            "row_index": row_index,
                            **row_data,
                        },
                    )
                )
                chunk_id += 1

        return chunks
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from docx import Document as DocxDocument

from .base_chunker import BaseChunker
from .schema import Document, DocumentChunk


class StructuredDocxChunker(BaseChunker):
    def split(self, document: Document) -> List[DocumentChunk]:
        file_path = document.metadata.get("file_path")
        if not file_path:
            raise ValueError("StructuredDocxChunker requires metadata['file_path']")

        path = Path(str(file_path)).resolve()
        doc = DocxDocument(str(path))

        parsed_rows: List[Dict[str, Any]] = []

        for table_index, table in enumerate(doc.tables):
            if len(table.rows) <= 1:
                continue

            headers = [self._clean_cell(cell.text) for cell in table.rows[0].cells]
            if not any(headers):
                continue

            for row_index, row in enumerate(table.rows[1:], start=1):
                cells = [self._clean_cell(cell.text) for cell in row.cells]
                if not any(cells):
                    continue

                row_data: Dict[str, str] = {}
                for i, value in enumerate(cells):
                    key = headers[i] if i < len(headers) and headers[i] else f"字段{i + 1}"
                    row_data[key] = value

                parsed_rows.append(
                    {
                        "table_index": table_index,
                        "row_index": row_index,
                        "row_data": row_data,
                    }
                )

        grouped = defaultdict(list)
        for item in parsed_rows:
            row_data = item["row_data"]
            spot_key = (
                row_data.get("景点ID")
                or row_data.get("景点名称")
                or f"table-{item['table_index']}-row-{item['row_index']}"
            )
            grouped[spot_key].append(item)

        chunks: List[DocumentChunk] = []
        chunk_index = 0

        for spot_key, items in grouped.items():
            merged_row_data = self._merge_rows([x["row_data"] for x in items])
            chunk_text = self._spot_to_text(merged_row_data)

            chunks.append(
                DocumentChunk(
                    chunk_id=f"structured-spot-{chunk_index}",
                    text=chunk_text,
                    metadata={
                        **document.metadata,
                        "chunk_type": "structured_spot",
                        "chunk_index": chunk_index,
                        "spot_key": spot_key,
                        "spot_id": merged_row_data.get("景点ID"),
                        "spot_name": merged_row_data.get("景点名称"),
                        "景区名称": merged_row_data.get("景区名称"),
                        "table_indexes": sorted({x["table_index"] for x in items}),
                        "row_indexes": [x["row_index"] for x in items],
                        **merged_row_data,
                    },
                )
            )
            chunk_index += 1

        return chunks

    @staticmethod
    def _clean_cell(text: str) -> str:
        if not text:
            return ""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _merge_rows(rows: List[Dict[str, str]]) -> Dict[str, str]:
        merged: Dict[str, List[str]] = defaultdict(list)

        for row in rows:
            for key, value in row.items():
                value = (value or "").strip()
                if value and value not in merged[key]:
                    merged[key].append(value)

        return {
            key: "；".join(values) if len(values) > 1 else values[0]
            for key, values in merged.items()
        }

    def _spot_to_text(self, row_data: Dict[str, str]) -> str:
        scenic_name = row_data.get("景区名称", "")
        spot_name = row_data.get("景点名称", "")
        spot_id = row_data.get("景点ID", "")
        location = row_data.get("具体位置", "")
        params = row_data.get("建筑/景观参数", "")
        function = row_data.get("核心功能", "")
        culture = row_data.get("文化内涵", "")
        intro = row_data.get("详细介绍", "")
        highlights = row_data.get("游玩亮点", "")
        open_info = row_data.get("演艺/开放信息", "")
        remark = row_data.get("备注", "")

        parts: List[str] = []

        summary_bits: List[str] = []
        if spot_name and scenic_name:
            summary_bits.append(f"{spot_name}位于{scenic_name}")
        elif spot_name:
            summary_bits.append(f"{spot_name}是一个景点")

        if location:
            summary_bits.append(f"具体位置在{location}")
        if function:
            summary_bits.append(f"核心功能是{function}")
        if highlights:
            summary_bits.append(f"游玩亮点包括{highlights}")
        if open_info:
            summary_bits.append(f"开放或演艺信息为{open_info}")

        if summary_bits:
            parts.append(self._clean_sentence("。".join(summary_bits) + "。"))

        detail_fields = [
            ("景区名称", scenic_name),
            ("景点ID", spot_id),
            ("景点名称", spot_name),
            ("具体位置", location),
            ("建筑/景观参数", params),
            ("核心功能", function),
            ("文化内涵", culture),
            ("详细介绍", intro),
            ("游玩亮点", highlights),
            ("演艺/开放信息", open_info),
            ("备注", remark),
        ]

        for key, value in detail_fields:
            if value:
                parts.append(f"{key}: {value}")

        known_keys = {k for k, _ in detail_fields}
        for key, value in row_data.items():
            if key not in known_keys and value:
                parts.append(f"{key}: {value}")

        return "\n".join(parts).strip()

    @staticmethod
    def _clean_sentence(text: str) -> str:
        text = re.sub(r"[。]{2,}", "。", text)
        text = re.sub(r"[，]{2,}", "，", text)
        return text.strip()

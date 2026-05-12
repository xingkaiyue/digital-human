import re
from typing import List, Tuple

from knowledge.chunker.schema import Document, DocumentChunk


class TextChunker:
    """
    适用于普通文本 / 指南类文档的 chunker。

    设计原则：
    1. 优先按段落切
    2. 段落过长再按句子切
    3. 句子过长再按弱边界切
    4. overlap 按语义单元回退，而不是按字符硬截
    """

    def __init__(self, chunk_size: int = 500, overlap: int = 100):
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")
        if overlap < 0:
            raise ValueError("overlap 不能小于 0")
        if overlap >= chunk_size:
            raise ValueError("overlap 必须小于 chunk_size")

        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, document: Document) -> List[DocumentChunk]:
        text = self._normalize_text(document.text)
        if not text:
            return []

        units = self._split_into_units(text)
        if not units:
            return []

        chunks: List[DocumentChunk] = []
        current_units: List[Tuple[str, int, int]] = []
        current_length = 0

        for unit_text, unit_start, unit_end in units:
            if not unit_text.strip():
                continue

            unit_len = len(unit_text)

            if not current_units:
                current_units.append((unit_text, unit_start, unit_end))
                current_length = unit_len
                continue

            if current_length + unit_len <= self.chunk_size:
                current_units.append((unit_text, unit_start, unit_end))
                current_length += unit_len
                continue

            chunks.append(
                self._build_chunk_from_units(
                    document=document,
                    chunk_index=len(chunks),
                    units=current_units,
                )
            )

            current_units = self._make_overlap_units(current_units)
            current_length = sum(len(x[0]) for x in current_units)

            if unit_len > self.chunk_size:
                oversized_parts = self._split_oversized_unit(unit_text, unit_start)
                for part_text, part_start, part_end in oversized_parts:
                    if current_units and current_length + len(part_text) > self.chunk_size:
                        chunks.append(
                            self._build_chunk_from_units(
                                document=document,
                                chunk_index=len(chunks),
                                units=current_units,
                            )
                        )
                        current_units = self._make_overlap_units(current_units)
                        current_length = sum(len(x[0]) for x in current_units)

                    current_units.append((part_text, part_start, part_end))
                    current_length += len(part_text)
            else:
                if current_units and current_length + unit_len > self.chunk_size:
                    chunks.append(
                        self._build_chunk_from_units(
                            document=document,
                            chunk_index=len(chunks),
                            units=current_units,
                        )
                    )
                    current_units = self._make_overlap_units(current_units)
                    current_length = sum(len(x[0]) for x in current_units)

                current_units.append((unit_text, unit_start, unit_end))
                current_length += unit_len

        if current_units:
            chunks.append(
                self._build_chunk_from_units(
                    document=document,
                    chunk_index=len(chunks),
                    units=current_units,
                )
            )

        return chunks

    def _split_into_units(self, text: str) -> List[Tuple[str, int, int]]:
        """
        返回 [(unit_text, start, end), ...]
        优先段落，再句子。
        """
        units: List[Tuple[str, int, int]] = []

        for para_text, para_start, para_end in self._split_paragraphs_with_offsets(text):
            stripped_para = para_text.strip()
            if not stripped_para:
                continue

            if len(stripped_para) <= self.chunk_size:
                units.append((stripped_para, para_start, para_start + len(stripped_para)))
                continue

            sentences = self._split_sentences_with_offsets(para_text, para_start)
            if not sentences:
                units.append((stripped_para, para_start, para_start + len(stripped_para)))
                continue

            for sent_text, sent_start, sent_end in sentences:
                sent_clean = sent_text.strip()
                if not sent_clean:
                    continue
                units.append((sent_clean, sent_start, sent_start + len(sent_clean)))

        return units

    def _split_paragraphs_with_offsets(self, text: str) -> List[Tuple[str, int, int]]:
        """
        按空行分段，并保留原文偏移。
        """
        result: List[Tuple[str, int, int]] = []
        pattern = re.compile(r".*?(?:\n\s*\n|$)", re.S)

        for match in pattern.finditer(text):
            block = match.group(0)
            if not block.strip():
                continue

            raw_start = match.start()
            stripped_block = block.strip()
            inner_offset = block.find(stripped_block)

            start = raw_start + inner_offset
            end = start + len(stripped_block)

            result.append((stripped_block, start, end))

        return result

    def _split_sentences_with_offsets(
        self, text: str, base_start: int
    ) -> List[Tuple[str, int, int]]:
        """
        中文友好的句切：
        - 句号、问号、感叹号、分号、冒号
        - 或显式换行
        """
        result: List[Tuple[str, int, int]] = []
        start = 0

        for match in re.finditer(r"[。！？!?；;：:](?:[”’\"']+)?|\n", text):
            end = match.end()
            part = text[start:end]
            if part.strip():
                trimmed = part.strip()
                inner_offset = part.find(trimmed)
                seg_start = base_start + start + inner_offset
                seg_end = seg_start + len(trimmed)
                result.append((trimmed, seg_start, seg_end))
            start = end

        if start < len(text):
            tail = text[start:]
            if tail.strip():
                trimmed = tail.strip()
                inner_offset = tail.find(trimmed)
                seg_start = base_start + start + inner_offset
                seg_end = seg_start + len(trimmed)
                result.append((trimmed, seg_start, seg_end))

        return result

    def _split_oversized_unit(self, text: str, base_start: int) -> List[Tuple[str, int, int]]:
        """
        对超长 unit 进行兜底切分：
        优先在弱边界切，不直接生硬按长度切。
        """
        parts: List[Tuple[str, int, int]] = []
        remaining = text
        current_offset = 0

        while len(remaining) > self.chunk_size:
            window = remaining[: self.chunk_size]
            cut = self._find_last_boundary(window)
            if cut <= 0:
                cut = self.chunk_size

            raw_piece = remaining[:cut]
            piece = raw_piece.strip()

            if piece:
                inner_offset = raw_piece.find(piece)
                start = base_start + current_offset + inner_offset
                end = start + len(piece)
                parts.append((piece, start, end))

            current_offset += cut
            remaining = remaining[cut:].lstrip()

            # 处理 lstrip 带来的额外偏移
            stripped_prefix_len = len(text[: current_offset]) - len(text[: current_offset].rstrip())
            if stripped_prefix_len > 0:
                pass

        if remaining.strip():
            piece = remaining.strip()
            inner_offset = remaining.find(piece)
            start = base_start + current_offset + inner_offset
            end = start + len(piece)
            parts.append((piece, start, end))

        return parts

    @staticmethod
    def _find_last_boundary(text: str) -> int:
        """
        在窗口中优先寻找较自然的切分位置。
        """
        boundary_patterns = [
            r"[，,、]\s*",
            r"\s+",
        ]

        best = -1
        for pattern in boundary_patterns:
            for match in re.finditer(pattern, text):
                best = max(best, match.end())

        return best

    def _make_overlap_units(
        self, units: List[Tuple[str, int, int]]
    ) -> List[Tuple[str, int, int]]:
        """
        overlap 按“最近若干语义单元”回退，而不是按字符截断。
        """
        if self.overlap <= 0 or not units:
            return []

        kept: List[Tuple[str, int, int]] = []
        total = 0

        for unit in reversed(units):
            kept.insert(0, unit)
            total += len(unit[0])
            if total >= self.overlap:
                break

        return kept

    def _build_chunk_from_units(
        self,
        document: Document,
        chunk_index: int,
        units: List[Tuple[str, int, int]],
    ) -> DocumentChunk:
        text = self._join_units([x[0] for x in units])
        start = units[0][1]
        end = units[-1][2]

        return DocumentChunk(
            chunk_id=str(chunk_index),
            text=text,
            metadata={
                **document.metadata,
                "chunk_index": chunk_index,
                "start": start,
                "end": end,
                "length": len(text),
                "unit_count": len(units),
                "text_preview": text[:120],
            },
        )

    @staticmethod
    def _join_units(units: List[str]) -> str:
        cleaned = []
        for unit in units:
            unit = unit.strip()
            if unit:
                cleaned.append(unit)
        return "\n".join(cleaned).strip()

    @staticmethod
    def _normalize_text(text: str) -> str:
        if not text:
            return ""

        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.rstrip() for line in text.split("\n")]
        normalized = "\n".join(lines)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

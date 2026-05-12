# extractors/table_parser.py
import re
from typing import List, Tuple
from .base_extractor import BaseExtractor


class TableParser(BaseExtractor):
    """解析Word文档中的表格，提取知识图谱三元组"""

    def extract(self, data=None) -> List[Tuple[str, str, str]]:
        return self.triplets

    def parse_tables(self, tables: List) -> List[Tuple[str, str, str]]:

        for table in tables:
            if not table or len(table) < 2:
                continue

            headers = table[0]
            print(f"📋 表头: {headers}")

            # 解析每一行数据（跳过表头）
            for row_idx, row in enumerate(table[1:], 2):
                if not row or len(row) < 3:
                    continue

                # 正确获取景点名称（第3列，索引2）
                scene_name = row[2].strip() if len(row) > 2 else ""

                # 跳过无效行
                if not scene_name or scene_name == '':
                    continue

                # 跳过表头行
                if scene_name in ['景点名称', '景区名称']:
                    continue

                # 景点名称已经是正确的短名称（如"灵山大照壁"、"五明桥"）
                print(f"   ✅ 第{row_idx}行: {scene_name}")

                # 1. 景区包含关系（第1列是景区名称）
                scenic_name = row[0].strip() if len(row) > 0 else ""
                if scenic_name and scenic_name not in ['景区名称', '']:
                    self.add_triplet(scenic_name, "包含", scene_name)

                # 2. 景点ID（第2列）
                scene_id = row[1].strip() if len(row) > 1 else ""
                if scene_id and scene_id not in ['景点ID', '']:
                    self.add_triplet(scene_name, "景点ID", scene_id)

                # 3. 具体位置（第4列）
                location = row[3].strip() if len(row) > 3 else ""
                if location and location not in ['具体位置', '']:
                    # 截取前50字
                    loc_short = location[:60] if len(location) > 60 else location
                    self.add_triplet(scene_name, "位于", loc_short)

                # 4. 建筑参数（第5列）- 提取数值
                architecture = row[4].strip() if len(row) > 4 else ""
                if architecture and architecture not in ['建筑/景观参数', '']:
                    self._extract_numbers(scene_name, architecture)
                    # 同时保存简短描述
                    arch_short = architecture[:80] if len(architecture) > 80 else architecture
                    self.add_triplet(scene_name, "建筑参数", arch_short)

                # 5. 核心功能（第6列）
                core_func = row[5].strip() if len(row) > 5 else ""
                if core_func and core_func not in ['核心功能', '']:
                    func_short = core_func[:80] if len(core_func) > 80 else core_func
                    self.add_triplet(scene_name, "核心功能", func_short)

                # 6. 文化内涵（第7列）
                culture = row[6].strip() if len(row) > 6 else ""
                if culture and culture not in ['文化内涵', '']:
                    culture_short = culture[:80] if len(culture) > 80 else culture
                    self.add_triplet(scene_name, "文化内涵", culture_short)

                # 7. 详细介绍（第8列）
                detail = row[7].strip() if len(row) > 7 else ""
                if detail and detail not in ['详细介绍', '']:
                    detail_short = detail[:100] if len(detail) > 100 else detail
                    self.add_triplet(scene_name, "详细介绍", detail_short)

                # 8. 游玩亮点（第9列）
                highlight = row[8].strip() if len(row) > 8 else ""
                if highlight and highlight not in ['游玩亮点', '']:
                    hl_short = highlight[:80] if len(highlight) > 80 else highlight
                    self.add_triplet(scene_name, "游玩亮点", hl_short)

                # 9. 开放信息（第10列）
                open_info = row[9].strip() if len(row) > 9 else ""
                if open_info and open_info not in ['演艺/开放信息', '']:
                    open_short = open_info[:80] if len(open_info) > 80 else open_info
                    self.add_triplet(scene_name, "开放信息", open_short)

                # 10. 备注（第11列）
                remark = row[10].strip() if len(row) > 10 else ""
                if remark and remark not in ['备注', '']:
                    remark_short = remark[:80] if len(remark) > 80 else remark
                    self.add_triplet(scene_name, "备注", remark_short)

        return self.triplets

    def _extract_numbers(self, scene_name: str, text: str):
        """提取数值参数"""
        if not text:
            return

        # 高度
        match = re.search(r'高(\d+(?:\.\d+)?)\s*[m米]', text)
        if match:
            self.add_triplet(scene_name, "高度", f"{match.group(1)}米")

        # 总高
        match = re.search(r'总高(\d+(?:\.\d+)?)\s*[m米]', text)
        if match:
            self.add_triplet(scene_name, "总高", f"{match.group(1)}米")

        # 长度
        match = re.search(r'长(\d+(?:\.\d+)?)\s*[m米]', text)
        if match:
            self.add_triplet(scene_name, "长度", f"{match.group(1)}米")

        # 宽度
        match = re.search(r'宽(\d+(?:\.\d+)?)\s*[m米]', text)
        if match:
            self.add_triplet(scene_name, "宽度", f"{match.group(1)}米")

        # 面积
        match = re.search(r'(\d+(?:\.\d+)?)\s*(?:㎡|平方米)', text)
        if match:
            self.add_triplet(scene_name, "面积", f"{match.group(1)}平方米")

        # 重量
        match = re.search(r'重(\d+(?:\.\d+)?)\s*吨', text)
        if match:
            self.add_triplet(scene_name, "重量", f"{match.group(1)}吨")

        # 占地
        match = re.search(r'占地(\d+(?:\.\d+)?)\s*(?:㎡|平方米|亩)', text)
        if match:
            self.add_triplet(scene_name, "占地面积", f"{match.group(1)}平方米")

    def add_triplet(self, subj: str, pred: str, obj: str):
        """添加三元组"""
        if not subj or not pred or not obj:
            return
        if len(subj) < 2 or len(obj) < 2:
            return
        # 过滤明显的垃圾数据
        garbage = ['', '无', '暂无', '全天开放', '免费', 'null', 'None']
        if obj in garbage:
            return
        triplet = (subj.strip(), pred.strip(), obj.strip())
        if triplet not in self.triplets:
            self.triplets.append(triplet)
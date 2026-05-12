from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


CATEGORY_TYPE_MAP = {
    "toilet": {"toilet"},
    "food": {"food"},
    "bus": {"bus"},
    "service": {"service"},
}


def normalize_point_type(raw_type: str, name: str = "") -> str:
    text = f"{raw_type or ''} {name or ''}".strip().lower()
    chinese_text = f"{raw_type or ''} {name or ''}"

    mappings = [
        ("toilet", ["toilet", "restroom", "wc", "厕所", "卫生间", "洗手间"]),
        ("food", ["food", "restaurant", "snack", "dining", "餐厅", "美食", "小吃", "餐饮"]),
        ("bus", ["bus", "station", "parking", "shuttle", "乘车点", "公交站", "观光车", "车站", "停车场", "上车点"]),
        ("service", ["service", "visitor center", "游客中心", "服务中心", "咨询处", "医务室"]),
        ("entrance", ["entrance", "gate", "入口", "大门", "检票"]),
        ("exit", ["exit", "出口"]),
        ("show", ["show", "performance", "演出", "表演"]),
        ("architecture", ["architecture", "building", "宫", "殿", "楼", "阁", "建筑"]),
        ("temple", ["temple", "monastery", "寺", "寺庙", "禅寺"]),
        ("core_spot", ["core", "landmark", "景点", "核心景点", "地标", "佛像", "大佛", "广场"]),
    ]

    for point_type, keywords in mappings:
        if any(keyword in text or keyword in chinese_text for keyword in keywords):
            return point_type
    return "poi"


def distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    radius = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return int(radius * c)


class PoiRepository:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _normalize_scenic_id(scenic_id: str) -> str:
        scenic_id = (scenic_id or "").strip()
        if not scenic_id:
            raise ValueError("scenic_id 不能为空")
        normalized = re.sub(r"[^0-9A-Za-z_\-]", "_", scenic_id)
        if not normalized:
            raise ValueError("scenic_id 非法")
        return normalized

    def _file_path(self, scenic_id: str) -> Path:
        return self.base_dir / f"{self._normalize_scenic_id(scenic_id)}.json"

    def load_scenic_pois(self, scenic_id: str) -> Optional[Dict[str, Any]]:
        file_path = self._file_path(scenic_id)
        if not file_path.exists():
            return None

        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"POI 文件格式错误: {file_path}")

        payload.setdefault("scenic_id", scenic_id)
        payload.setdefault("scenic_name", None)
        payload.setdefault("pois", [])
        payload.setdefault("meta", {})
        return payload

    def get_pois(self, scenic_id: str) -> List[Dict[str, Any]]:
        payload = self.load_scenic_pois(scenic_id)
        if not payload:
            return []
        return [dict(item) for item in payload.get("pois", []) if isinstance(item, dict)]

    def list_scenic_pois(self, scenic_id: str) -> Dict[str, Any]:
        payload = self.load_scenic_pois(scenic_id)
        if not payload:
            return {
                "scenic_id": self._normalize_scenic_id(scenic_id),
                "scenic_name": None,
                "pois": [],
                "meta": {},
            }
        return payload

    def save_pois(
        self,
        scenic_id: str,
        scenic_name: str | None,
        pois: List[Dict[str, Any]],
        overwrite: bool = True,
        meta: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        file_path = self._file_path(scenic_id)
        if file_path.exists() and not overwrite:
            raise ValueError(f"景区 {scenic_id} 的 POI 数据已存在，请将 overwrite 设为 true")

        payload = {
            "scenic_id": self._normalize_scenic_id(scenic_id),
            "scenic_name": scenic_name,
            "pois": pois,
            "meta": meta or {},
        }
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def find_poi(self, scenic_id: str, value: str | None) -> Optional[Dict[str, Any]]:
        if not value:
            return None
        query = value.strip()
        if not query:
            return None

        pois = self.get_pois(scenic_id)
        for poi in pois:
            if poi.get("poi_id") == query or poi.get("name") == query:
                return poi

        for poi in pois:
            aliases = poi.get("aliases") or []
            if query in aliases:
                return poi

        for poi in pois:
            name = str(poi.get("name") or "")
            aliases = [str(alias) for alias in poi.get("aliases") or []]
            if query in name or name in query:
                return poi
            if any(query in alias or alias in query for alias in aliases):
                return poi
        return None

    def filter_valid_route_pois(self, scenic_id: str) -> List[Dict[str, Any]]:
        pois = self.get_pois(scenic_id)
        valid: List[Dict[str, Any]] = []
        for poi in pois:
            try:
                lat = float(poi["lat"])
                lng = float(poi["lng"])
            except (KeyError, TypeError, ValueError):
                continue
            if not poi.get("name") or not poi.get("poi_id"):
                continue
            copied = dict(poi)
            copied["lat"] = lat
            copied["lng"] = lng
            copied["point_type"] = normalize_point_type(str(copied.get("point_type") or ""), str(copied.get("name") or ""))
            valid.append(copied)
        return valid

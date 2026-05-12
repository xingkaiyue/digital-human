from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional


@dataclass
class POICandidate:
    name: str
    scenic_id: Optional[str]
    scenic_name: Optional[str]
    location: Optional[str]
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


class POIResolver:
    """
    基于当前知识库中的结构化景点，做 POI 归一化解析。
    适合 route / recommend / knowledge 的点位理解。
    """

    def __init__(
        self,
        knowledge_service: Optional[Any] = None,
        custom_pois: Optional[List[Dict[str, Any]]] = None,
        debug: bool = False,
    ):
        self.knowledge_service = knowledge_service
        self.custom_pois = custom_pois or []
        self.debug = debug

    def resolve(
        self,
        query_name: str,
        scene_context: Optional[Any] = None,
        top_k: int = 3,
    ) -> List[POICandidate]:
        query_name = (query_name or "").strip()
        if not query_name:
            return []

        poi_records = self._load_poi_records(scene_context)
        if self.debug:
            print(f"[POIResolver] query={query_name} loaded_poi_count={len(poi_records)}")

        candidates: List[POICandidate] = []

        for record in poi_records:
            score = self._score_candidate(query_name, record)
            if score <= 0:
                continue

            metadata = record.get("metadata", {}) or {}
            candidates.append(
                POICandidate(
                    name=record.get("name") or "",
                    scenic_id=metadata.get("scenic_id"),
                    scenic_name=metadata.get("scenic_name") or metadata.get("景区名称"),
                    location=metadata.get("具体位置"),
                    metadata=metadata,
                    score=score,
                )
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:top_k]

    def resolve_one(
        self,
        query_name: str,
        scene_context: Optional[Any] = None,
    ) -> Optional[POICandidate]:
        result = self.resolve(query_name=query_name, scene_context=scene_context, top_k=1)
        return result[0] if result else None

    def resolve_route_slots(
        self,
        start_name: Optional[str],
        end_name: Optional[str],
        scene_context: Optional[Any] = None,
    ) -> Dict[str, Any]:
        resolved: Dict[str, Any] = {
            "start_name": start_name,
            "end_name": end_name,
            "start_poi": None,
            "end_poi": None,
            "missing_slots": [],
        }

        if start_name:
            resolved["start_poi"] = self.resolve_one(start_name, scene_context=scene_context)

        if end_name:
            resolved["end_poi"] = self.resolve_one(end_name, scene_context=scene_context)
        else:
            resolved["missing_slots"].append("end_name")

        return resolved

    def _load_poi_records(self, scene_context: Optional[Any]) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []

        if self.knowledge_service is not None:
            spots = self.knowledge_service.list_spots(scene_context=scene_context, limit=None)

            if self.debug:
                print(f"[POIResolver] knowledge_service.list_spots returned {type(spots)}")

            for item in spots:
                metadata = self._extract_metadata(item)
                if not metadata:
                    continue

                spot_name = metadata.get("spot_name") or metadata.get("景点名称")
                if not spot_name:
                    continue

                records.append(
                    {
                        "name": spot_name,
                        "aliases": self._build_aliases(spot_name),
                        "metadata": metadata,
                    }
                )

        for item in self.custom_pois:
            name = item.get("name")
            if not name:
                continue
            aliases = item.get("aliases") or self._build_aliases(name)
            metadata = item.get("metadata", {}) or {}
            records.append(
                {
                    "name": name,
                    "aliases": aliases,
                    "metadata": metadata,
                }
            )

        return records

    def _extract_metadata(self, item: Any) -> Dict[str, Any]:
        """
        兼容多种返回格式：
        1. 对象：item.metadata
        2. dict：item["metadata"]
        3. 直接就是 metadata dict
        """
        if item is None:
            return {}

        if isinstance(item, dict):
            if "metadata" in item and isinstance(item["metadata"], dict):
                return item["metadata"] or {}
            # 如果本身就是 metadata
            if "景点名称" in item or "spot_name" in item or "scenic_id" in item:
                return item

        metadata = getattr(item, "metadata", None)
        if isinstance(metadata, dict):
            return metadata or {}

        return {}

    def _score_candidate(self, query_name: str, record: Dict[str, Any]) -> float:
        query = query_name.strip()
        name = (record.get("name") or "").strip()
        aliases = record.get("aliases") or []

        if not query or not name:
            return 0.0

        best_score = 0.0

        all_names = [name] + list(aliases)
        for alias in all_names:
            alias = (alias or "").strip()
            if not alias:
                continue

            if query == alias:
                best_score = max(best_score, 1.0)
                continue

            if query in alias or alias in query:
                best_score = max(best_score, 0.92)
                continue

            simplified_alias = self._simplify_name(alias)
            simplified_query = self._simplify_name(query)
            if simplified_query and simplified_alias:
                if simplified_query == simplified_alias:
                    best_score = max(best_score, 0.95)
                    continue
                if simplified_query in simplified_alias or simplified_alias in simplified_query:
                    best_score = max(best_score, 0.88)
                    continue

            similarity = SequenceMatcher(
                None,
                simplified_query or query,
                simplified_alias or alias,
            ).ratio()

            if similarity >= 0.70:
                best_score = max(best_score, similarity * 0.85)

        return round(best_score, 4)

    def _build_aliases(self, name: str) -> List[str]:
        name = (name or "").strip()
        if not name:
            return []

        aliases = {name}

        if name.startswith("灵山") and len(name) > 2:
            aliases.add(name[2:])

        if name.startswith("拈花湾") and len(name) > 3:
            aliases.add(name[3:])

        simplified = self._simplify_name(name)
        if simplified:
            aliases.add(simplified)

        manual_alias_map = {
            "灵山梵宫": ["梵宫"],
            "灵山大佛": ["大佛"],
            "祥符禅寺": ["禅寺"],
            "佛教文化博览馆": ["博览馆", "文化博览馆"],
            "五印坛城": ["坛城"],
            "百子戏弥勒": ["弥勒"],
            "拈花广场": ["广场"],
            "香月花街": ["花街"],
        }
        for full_name, extra_aliases in manual_alias_map.items():
            if name == full_name:
                aliases.update(extra_aliases)

        return sorted(item for item in aliases if item)

    @staticmethod
    def _simplify_name(name: str) -> str:
        name = (name or "").strip()
        removable_prefixes = ["灵山", "拈花湾", "拈花"]
        removable_suffixes = ["禅意小镇", "景区", "景点"]

        for prefix in removable_prefixes:
            if name.startswith(prefix) and len(name) > len(prefix):
                name = name[len(prefix):]
                break

        for suffix in removable_suffixes:
            if name.endswith(suffix) and len(name) > len(suffix):
                name = name[: -len(suffix)]
                break

        return name.strip()

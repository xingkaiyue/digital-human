from __future__ import annotations

from typing import Any, Dict, List

from api.schemas import NearbyResponse
from services.poi_repository import CATEGORY_TYPE_MAP, PoiRepository, distance_meters, normalize_point_type


CATEGORY_KEYWORDS = {
    "toilet": ["厕所", "卫生间", "洗手间"],
    "food": ["美食", "餐厅", "小吃", "餐饮"],
    "bus": ["乘车点", "公交站", "观光车", "停车场", "上车点"],
    "service": ["游客中心", "服务中心", "咨询处", "医务室"],
}


class NearbyService:
    def __init__(self, repository: PoiRepository, tencent_map_client: Any | None = None) -> None:
        self.repository = repository
        self.tencent_map_client = tencent_map_client

    def search_nearby(
        self,
        scenic_id: str,
        center: Dict[str, Any],
        categories: List[str],
        radius_m: int = 500,
        limit: int = 10,
    ) -> NearbyResponse:
        categories = categories or ["toilet", "food", "bus", "service"]
        debug: Dict[str, Any] = {"tencent_errors": []}
        results: Dict[str, List[Dict[str, Any]]] = {}

        for category in categories:
            local_items = self.search_local_nearby(
                scenic_id=scenic_id,
                center_lat=center["lat"],
                center_lng=center["lng"],
                category=category,
                radius_m=radius_m,
                limit=limit,
            )
            tencent_items: List[Dict[str, Any]] = []
            if len(local_items) < limit:
                try:
                    tencent_items = self.search_tencent_nearby(
                        lat=center["lat"],
                        lng=center["lng"],
                        category=category,
                        radius_m=radius_m,
                        limit=limit,
                    )
                except Exception as exc:
                    debug["tencent_errors"].append({"category": category, "error": str(exc)})

            results[category] = self.merge_and_deduplicate_results(local_items, tencent_items, limit=limit)

        flat_pois: List[Dict[str, Any]] = []
        for category_items in results.values():
            flat_pois.extend(category_items)

        return NearbyResponse(
            scenic_id=scenic_id,
            center=center,
            radius_m=radius_m,
            results=results,
            ui_command={
                "type": "display_nearby_pois",
                "center": center,
                "pois": flat_pois,
            },
            message="已找到附近厕所、美食、乘车点等信息",
            debug=debug,
        )

    def search_local_nearby(
        self,
        scenic_id: str,
        center_lat: float,
        center_lng: float,
        category: str,
        radius_m: int = 500,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        pois = self.repository.filter_valid_route_pois(scenic_id)
        matched: List[Dict[str, Any]] = []
        keywords = CATEGORY_KEYWORDS.get(category, [])

        for poi in pois:
            point_type = normalize_point_type(str(poi.get("point_type") or ""), str(poi.get("name") or ""))
            haystack = " ".join(
                [
                    str(poi.get("name") or ""),
                    str(poi.get("intro") or ""),
                    str(poi.get("address") or ""),
                    " ".join(str(tag) for tag in poi.get("tags") or []),
                ]
            )
            if point_type not in CATEGORY_TYPE_MAP.get(category, set()) and not any(keyword in haystack for keyword in keywords):
                continue

            distance_m = distance_meters(center_lat, center_lng, poi["lat"], poi["lng"])
            if distance_m > radius_m:
                continue

            matched.append(
                {
                    "name": poi["name"],
                    "address": poi.get("address", ""),
                    "lat": poi["lat"],
                    "lng": poi["lng"],
                    "distance_m": distance_m,
                    "category": category,
                    "source": "local_poi",
                    "poi_id": poi.get("poi_id"),
                    "point_type": point_type,
                }
            )

        matched.sort(key=lambda item: item["distance_m"])
        return matched[:limit]

    def search_tencent_nearby(
        self,
        lat: float,
        lng: float,
        category: str,
        radius_m: int = 500,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        if self.tencent_map_client is None:
            return []

        results: List[Dict[str, Any]] = []
        for keyword in CATEGORY_KEYWORDS.get(category, []):
            items = self.tencent_map_client.search_nearby(
                lat=lat,
                lng=lng,
                keyword=keyword,
                radius=radius_m,
                page_size=limit,
            )
            for item in items:
                location = item.get("location") or {}
                item_lat = location.get("lat")
                item_lng = location.get("lng")
                if item_lat is None or item_lng is None:
                    continue
                results.append(
                    {
                        "name": item.get("title") or item.get("name") or keyword,
                        "address": item.get("address", ""),
                        "lat": float(item_lat),
                        "lng": float(item_lng),
                        "distance_m": distance_meters(lat, lng, float(item_lat), float(item_lng)),
                        "category": category,
                        "source": "tencent_nearby",
                        "poi_id": None,
                        "point_type": category,
                    }
                )
        return results

    def merge_and_deduplicate_results(
        self,
        local_items: List[Dict[str, Any]],
        tencent_items: List[Dict[str, Any]],
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in [*local_items, *tencent_items]:
            key = f"{item.get('name','')}|{round(float(item.get('lat', 0)), 5)}|{round(float(item.get('lng', 0)), 5)}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        merged.sort(key=lambda item: item.get("distance_m", 0))
        return merged[:limit]

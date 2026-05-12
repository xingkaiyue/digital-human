from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Dict, List, Optional

import requests


class TencentMapClient:
    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.key = getattr(settings, "tencent_map_key", None)
        self.sk = getattr(settings, "tencent_map_sk", None)
        self.base_url = "https://apis.map.qq.com"
        self.direction_path_map = {
            "walk": "/ws/direction/v1/walking",
            "drive": "/ws/direction/v1/driving",
            "bike": "/ws/direction/v1/bicycling",
        }

    @staticmethod
    def _build_sig(path: str, raw_params: Dict[str, Any], sk: str) -> tuple[str, str]:
        sorted_items = sorted(raw_params.items(), key=lambda item: item[0])
        sign_query_string = "&".join(f"{key}={value}" for key, value in sorted_items)
        sig_raw = f"{path}?{sign_query_string}{sk}"
        sig = hashlib.md5(sig_raw.encode("utf-8")).hexdigest()
        return sig, sign_query_string

    def _signed_get(self, path: str, raw_params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.key:
            raise ValueError("未配置腾讯地图 key，请检查 settings.tencent_map_key")
        if not self.sk:
            raise ValueError("未配置腾讯地图 sk，请检查 settings.tencent_map_sk")

        raw_params = {
            key: value
            for key, value in dict(raw_params).items()
            if value is not None and value != ""
        }

        raw_params["key"] = self.key
        raw_params["output"] = "json"

        sig, _ = self._build_sig(path=path, raw_params=raw_params, sk=self.sk)

        final_params = dict(sorted(raw_params.items(), key=lambda item: item[0]))
        final_params["sig"] = sig

        response = requests.get(
            f"{self.base_url}{path}",
            params=final_params,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") != 0:
            raise ValueError(
                f"腾讯接口调用失败: path={path}, status={data.get('status')}, "
                f"message={data.get('message')}, request_id={data.get('request_id')}"
            )

        return data

    @staticmethod
    def _decode_polyline(polyline: List[float]) -> List[Dict[str, float]]:
        if not isinstance(polyline, list) or len(polyline) < 2:
            return []

        decoded = [float(item) for item in polyline]
        for index in range(2, len(decoded)):
            decoded[index] = decoded[index - 2] + decoded[index] / 1_000_000.0

        points: List[Dict[str, float]] = []
        for index in range(0, len(decoded), 2):
            if index + 1 < len(decoded):
                points.append(
                    {
                        "lat": round(decoded[index], 6),
                        "lng": round(decoded[index + 1], 6),
                    }
                )

        return points

    @staticmethod
    def _estimate_duration_min(mode: str, distance_m: int, raw_duration_sec: int) -> int:
        if raw_duration_sec and raw_duration_sec > 0:
            return max(1, math.ceil(raw_duration_sec / 60))

        if distance_m <= 0:
            return 0

        speed_m_per_min = {
            "walk": 75,
            "bike": 220,
            "drive": 350,
        }.get((mode or "").lower(), 75)

        return max(1, math.ceil(distance_m / speed_m_per_min))

    def search_place(
        self,
        keyword: str,
        region: str | None = None,
        boundary: str | None = None,
        page_size: int = 10,
    ) -> List[Dict[str, Any]]:
        keyword = self._clean_query(keyword)
        if not keyword:
            return []

        region = self._clean_region(region) or "无锡"
        resolved_boundary = boundary or f"region({region},0)"

        data = self._signed_get(
            path="/ws/place/v1/search",
            raw_params={
                "keyword": keyword,
                "boundary": resolved_boundary,
                "page_size": page_size,
                "page_index": 1,
            },
        )

        return data.get("data", []) or []

    def geocode(self, address: str, region: str | None = None) -> Optional[Dict[str, Any]]:
        address = self._clean_query(address)
        if not address:
            return None

        data = self._signed_get(
            path="/ws/geocoder/v1/",
            raw_params={
                "address": address,
                "region": self._clean_region(region) or "无锡",
            },
        )

        result = data.get("result") or {}
        location = result.get("location") or {}

        if "lat" not in location or "lng" not in location:
            return None

        return {
            "name": result.get("title") or address,
            "address": result.get("address") or address,
            "lat": float(location["lat"]),
            "lng": float(location["lng"]),
            "source": "tencent_geocode",
            "raw": data,
        }

    def search_nearby(
        self,
        lat: float,
        lng: float,
        keyword: str,
        radius: int = 500,
        page_size: int = 10,
    ) -> List[Dict[str, Any]]:
        data = self._signed_get(
            path="/ws/place/v1/search",
            raw_params={
                "keyword": keyword,
                "boundary": f"nearby({lat},{lng},{radius},0)",
                "orderby": "_distance",
                "page_size": page_size,
                "page_index": 1,
            },
        )

        return data.get("data", []) or []

    def resolve_poi_location(
        self,
        name: str,
        scenic_name: str | None = None,
        city: str | None = None,
        address_hint: str | None = None,
        address: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        """
        解析景区内部 POI 坐标。

        不使用人工坐标。
        不生成假坐标。
        只通过腾讯位置服务 geocoder / place search 解析。

        重点修复：
        1. region 只使用城市，不使用 scenic_name。
        2. address_hint 不再覆盖 address，而是组合多个查询词。
        3. 对景区内部相对地址，优先用 “城市 + 景区名 + POI 名称” 搜索。
        4. 对结果做相关性筛选，避免搜到其他城市或无关 POI。
        """

        name = self._clean_query(name)
        scenic_name = self._clean_query(scenic_name)
        city = self._clean_region(city) or "无锡"
        address_hint = self._clean_query(address_hint)
        address = self._clean_query(address)

        if not name:
            return None

        scenic_candidates = self._build_scenic_candidates(scenic_name=scenic_name, address_hint=address_hint)
        query_candidates = self._build_location_queries(
            name=name,
            city=city,
            scenic_candidates=scenic_candidates,
            address_hint=address_hint,
            address=address,
        )

        errors: List[str] = []

        # 1. 优先 place search。景区内部点位更适合搜索，而不是纯地址解析。
        for keyword in query_candidates:
            try:
                items = self.search_place(keyword=keyword, region=city, page_size=10)
            except Exception as exc:
                errors.append(f"search_place({keyword}) failed: {exc}")
                continue

            matched = self._pick_best_place_item(
                items=items,
                name=name,
                scenic_candidates=scenic_candidates,
                city=city,
            )
            if matched:
                return matched

        # 2. 再尝试 geocoder。适合比较像真实地址的文本。
        for keyword in query_candidates:
            try:
                result = self.geocode(address=keyword, region=city)
            except Exception as exc:
                errors.append(f"geocode({keyword}) failed: {exc}")
                continue

            if result and self._is_reasonable_result(
                item=result,
                name=name,
                scenic_candidates=scenic_candidates,
                city=city,
            ):
                result["source"] = "tencent_geocode"
                return result

        # 3. 最后尝试只搜景区大名，至少确认腾讯服务本身是否可用。
        # 注意：这里不会返回景区大坐标作为 POI 坐标，只用于 debug。
        self.last_resolve_errors = {
            "name": name,
            "city": city,
            "scenic_name": scenic_name,
            "address_hint": address_hint,
            "address": address,
            "queries": query_candidates,
            "errors": errors,
        }

        return None

    def _build_location_queries(
        self,
        name: str,
        city: str,
        scenic_candidates: List[str],
        address_hint: str | None,
        address: str | None,
    ) -> List[str]:
        queries: List[str] = []

        def add(value: str | None) -> None:
            value = self._clean_query(value)
            if value and value not in queries:
                queries.append(value)

        for scenic in scenic_candidates:
            add(f"{city} {scenic} {name}")
            add(f"{city}{scenic}{name}")
            add(f"{scenic} {name}")
            add(f"{scenic}{name}")
            add(f"{name} {scenic}")

        if address_hint:
            add(f"{city} {address_hint} {name}")
            add(f"{address_hint} {name}")
            add(f"{address_hint}{name}")

        if address:
            # address 是“九龙灌浴北侧...”这种相对位置时，必须加上景区和城市。
            for scenic in scenic_candidates:
                add(f"{city} {scenic} {address} {name}")
                add(f"{city} {scenic} {name} {address}")

            add(f"{city} {address} {name}")
            add(f"{address} {name}")

        add(f"{city} {name}")
        add(name)

        return queries

    def _build_scenic_candidates(
        self,
        scenic_name: str | None,
        address_hint: str | None,
    ) -> List[str]:
        candidates: List[str] = []

        def add(value: str | None) -> None:
            value = self._clean_query(value)
            if value and value not in candidates:
                candidates.append(value)

        add(scenic_name)
        add(address_hint)

        # 你的场景强相关别名。
        # 不是人工坐标，只是搜索关键词增强。
        combined = f"{scenic_name or ''} {address_hint or ''}"
        if "灵山" in combined:
            add("灵山胜境")
            add("灵山大佛")
            add("灵山大佛景区")
            add("无锡灵山胜境")
            add("无锡灵山大佛景区")
            add("灵山景区")

        if "拈花" in combined:
            add("拈花湾")
            add("拈花湾禅意小镇")
            add("无锡拈花湾")
            add("无锡拈花湾禅意小镇")

        if not candidates:
            add("灵山胜境")

        return candidates

    def _pick_best_place_item(
        self,
        items: List[Dict[str, Any]],
        name: str,
        scenic_candidates: List[str],
        city: str,
    ) -> Optional[Dict[str, Any]]:
        if not items:
            return None

        scored_items: List[tuple[int, Dict[str, Any]]] = []

        for item in items:
            location = item.get("location") or {}
            if "lat" not in location or "lng" not in location:
                continue

            score = self._score_place_item(
                item=item,
                name=name,
                scenic_candidates=scenic_candidates,
                city=city,
            )

            if score <= 0:
                continue

            scored_items.append((score, item))

        if not scored_items:
            return None

        scored_items.sort(key=lambda pair: pair[0], reverse=True)
        best_score, best_item = scored_items[0]

        # 分数太低说明结果相关性不够，宁可失败，不要乱入库。
        if best_score < 30:
            return None

        location = best_item.get("location") or {}

        return {
            "name": best_item.get("title") or best_item.get("name") or name,
            "address": best_item.get("address") or "",
            "lat": float(location["lat"]),
            "lng": float(location["lng"]),
            "source": "tencent_search",
            "raw": best_item,
            "match_score": best_score,
        }

    def _score_place_item(
        self,
        item: Dict[str, Any],
        name: str,
        scenic_candidates: List[str],
        city: str,
    ) -> int:
        title = str(item.get("title") or item.get("name") or "")
        address = str(item.get("address") or "")
        category = str(item.get("category") or "")
        province = str(item.get("ad_info", {}).get("province") or "")
        item_city = str(item.get("ad_info", {}).get("city") or "")

        haystack = f"{title} {address} {category} {province} {item_city}"

        score = 0

        if name and name == title:
            score += 80
        elif name and (name in title or title in name):
            score += 50
        elif name and name in haystack:
            score += 35

        for scenic in scenic_candidates:
            if scenic and scenic in haystack:
                score += 25

        if city and city in haystack:
            score += 20

        if "无锡" in haystack:
            score += 15

        if "灵山" in haystack:
            score += 15

        if "拈花湾" in haystack:
            score += 15

        # 排除明显不相关城市
        if city and item_city and city not in item_city and item_city not in city:
            score -= 50

        return score

    def _is_reasonable_result(
        self,
        item: Dict[str, Any],
        name: str,
        scenic_candidates: List[str],
        city: str,
    ) -> bool:
        address = str(item.get("address") or "")
        result_name = str(item.get("name") or "")
        haystack = f"{result_name} {address}"

        if name and name in haystack:
            return True

        if city and city in haystack and any(scenic in haystack for scenic in scenic_candidates):
            return True

        return False

    @staticmethod
    def _clean_query(value: str | None) -> str:
        if value is None:
            return ""

        text = str(value).strip()
        text = text.replace("\xa0", " ")
        text = text.replace("\u3000", " ")
        text = re.sub(r"\s+", " ", text)

        # Swagger 默认值 string 不应该参与查询
        if text.lower() in {"string", "none", "null", "undefined"}:
            return ""

        return text.strip()

    @staticmethod
    def _clean_region(value: str | None) -> str:
        if value is None:
            return ""

        text = str(value).strip()
        text = text.replace("市", "")
        text = text.replace("中国", "")
        text = re.sub(r"\s+", "", text)

        if text.lower() in {"string", "none", "null", "undefined"}:
            return ""

        return text or "无锡"

    def plan_route(
        self,
        start: Dict[str, Any],
        end: Dict[str, Any],
        waypoints: Optional[List[Dict[str, Any]]] = None,
        mode: str = "walk",
    ) -> Dict[str, Any]:
        waypoints = waypoints or []
        mode = (mode or "walk").strip().lower()

        path = self.direction_path_map.get(mode)
        if not path:
            raise ValueError(f"不支持的路线模式: {mode}，当前仅支持 walk / drive / bike")

        raw_params: Dict[str, Any] = {
            "from": f"{float(start['lat'])},{float(start['lng'])}",
            "to": f"{float(end['lat'])},{float(end['lng'])}",
        }

        if waypoints:
            raw_params["waypoints"] = ";".join(
                f"{float(item['lat'])},{float(item['lng'])}"
                for item in waypoints
            )

        data = self._signed_get(path=path, raw_params=raw_params)

        routes = data.get("result", {}).get("routes", []) or []
        if not routes:
            raise ValueError("腾讯路线规划返回为空 routes")

        route = routes[0]
        route_distance = int(route.get("distance", 0) or 0)
        raw_route_duration_sec = int(route.get("duration", 0) or 0)

        steps: List[Dict[str, Any]] = []

        for index, item in enumerate(route.get("steps", []) or [], start=1):
            distance_m = int(item.get("distance", 0) or 0)
            raw_step_duration_sec = int(item.get("duration", 0) or 0)
            duration_min = self._estimate_duration_min(
                mode=mode,
                distance_m=distance_m,
                raw_duration_sec=raw_step_duration_sec,
            )

            steps.append(
                {
                    "seq_no": index,
                    "instruction": (item.get("instruction") or "继续前行").strip(),
                    "distance_m": distance_m,
                    "duration_min": duration_min,
                }
            )

        step_total_duration_min = sum(item["duration_min"] for item in steps)
        route_duration_min = max(
            self._estimate_duration_min(
                mode=mode,
                distance_m=route_distance,
                raw_duration_sec=raw_route_duration_sec,
            ),
            step_total_duration_min,
        )

        parsed_waypoints = [
            {
                "poi_id": wp.get("poi_id", ""),
                "name": wp.get("name", ""),
                "lat": float(wp["lat"]),
                "lng": float(wp["lng"]),
                "point_type": wp.get("point_type", "waypoint"),
                "stay_minutes": wp.get("stay_minutes"),
                "intro": wp.get("intro"),
            }
            for wp in waypoints
        ]

        polyline_points = self._decode_polyline(route.get("polyline", []) or [])

        return {
            "distance_m": route_distance,
            "duration_min": route_duration_min,
            "steps": steps,
            "waypoints": parsed_waypoints,
            "polyline": polyline_points,
            "raw_response": data,
            "debug": {
                "path": path,
                "request_id": data.get("request_id"),
                "mode": mode,
                "polyline_point_count": len(polyline_points),
            },
        }

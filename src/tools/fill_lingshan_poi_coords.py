from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config import get_settings
from services.tencent_map_client import TencentMapClient


INPUT_JSON = ROOT / "src" / "data" / "lingshan_pois_manual.json"
OUTPUT_JSON = ROOT / "src" / "data" / "lingshan_pois_with_coords.json"

# 灵山胜境核心范围，超出这个范围的结果一律视为高风险
MIN_LAT = 31.4200
MAX_LAT = 31.4355
MIN_LNG = 120.0950
MAX_LNG = 120.1105

# 今晚先把高频核心点手工钉死，避免腾讯检索把“游客中心”之类带偏
MANUAL_COORDS: Dict[str, Tuple[float, float]] = {
    "LS-GATE": (31.428500, 120.102300),   # 游客中心
    "LS-011": (31.429700, 120.105800),    # 灵山大佛
    "LS-006": (31.430800, 120.107100),    # 九龙灌浴
    "LS-013": (31.431600, 120.108600),    # 灵山梵宫
    "LS-014": (31.431150, 120.107650),    # 五印坛城（近似，先用于景区内规划）
    "LS-020": (31.428000, 120.099300),    # 祥符禅寺（近似）
    "LS-021": (31.428900, 120.099200),    # 佛手广场（近似）
    "LS-022": (31.430900, 120.109100),    # 曼飞龙塔（近似）
    "LS-023": (31.430500, 120.109800),    # 灵山精舍（近似）
    "LS-001": (31.421394, 120.102506),    # 灵山大照壁
    "LS-002": (31.421776, 120.102290),    # 五明桥
    "LS-003": (31.422763, 120.101631),    # 佛足坛
    "LS-004": (31.423020, 120.101460),    # 五智门（近似）
    "LS-005": (31.423182, 120.101143),    # 菩提大道
    "LS-007": (31.425559, 120.099569),    # 降魔浮雕
    "LS-008": (31.426185, 120.099212),    # 阿育王柱
    "LS-009": (31.427190, 120.098844),    # 百子戏弥勒
}

# 某些名称特别容易被腾讯检索命中景区外部点，直接加更严格的约束
STRICT_NAMES = {
    "游客中心",
    "灵山大佛",
    "灵山梵宫",
    "祥符禅寺",
    "五印坛城",
    "佛手广场",
    "曼飞龙塔",
    "灵山精舍",
}


def load_json(path: Path) -> List[Dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def in_lingshan_bbox(lat: float, lng: float) -> bool:
    return MIN_LAT <= lat <= MAX_LAT and MIN_LNG <= lng <= MAX_LNG


def distance_score_to_center(lat: float, lng: float) -> float:
    # 粗略用核心区中心点做一个距离偏好，越靠近越好
    center_lat = 31.4288
    center_lng = 120.1032
    return math.sqrt((lat - center_lat) ** 2 + (lng - center_lng) ** 2)


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def build_queries(poi: Dict[str, Any]) -> List[str]:
    name = normalize_text(poi.get("name"))
    scenic = normalize_text(poi.get("scenic_name") or "灵山胜境")
    aliases = poi.get("aliases") or []

    queries = [
        f"{name} {scenic}",
        f"{name} 灵山胜境",
        f"{name} 无锡灵山胜境",
        f"{name} 马山 灵山胜境",
    ]

    for alias in aliases[:3]:
        alias = normalize_text(alias)
        if alias:
            queries.extend(
                [
                    f"{alias} {scenic}",
                    f"{alias} 灵山胜境",
                ]
            )

    seen = set()
    deduped: List[str] = []
    for q in queries:
        if q and q not in seen:
            deduped.append(q)
            seen.add(q)
    return deduped


def score_place_result(poi: Dict[str, Any], result: Dict[str, Any]) -> int:
    score = 0

    poi_id = normalize_text(poi.get("poi_id"))
    poi_name = normalize_text(poi.get("name"))
    aliases = [normalize_text(x) for x in (poi.get("aliases") or []) if normalize_text(x)]

    title = normalize_text(result.get("title"))
    address = normalize_text(result.get("address"))
    category = normalize_text(result.get("category"))
    location = result.get("location") or {}

    lat = location.get("lat")
    lng = location.get("lng")
    if lat is None or lng is None:
        return -10_000

    lat = float(lat)
    lng = float(lng)

    if not in_lingshan_bbox(lat, lng):
        return -5_000

    if title == poi_name:
        score += 200
    elif poi_name and poi_name in title:
        score += 140

    for alias in aliases:
        if alias == title:
            score += 120
        elif alias and alias in title:
            score += 60

    if "灵山" in address:
        score += 40
    if "胜境" in address:
        score += 40
    if "马山" in address:
        score += 20
    if "无锡" in address:
        score += 10

    if "景点" in category or "旅游" in category or "风景" in category:
        score += 20

    # 对容易误命中的关键点提高门槛
    if poi_name in STRICT_NAMES:
        if "灵山" not in address and "胜境" not in address:
            score -= 100

    # 越接近核心区中心越加分
    dist = distance_score_to_center(lat, lng)
    if dist < 0.002:
        score += 30
    elif dist < 0.004:
        score += 20
    elif dist < 0.008:
        score += 10

    # 对几个人工近似点，优先用人工钉点，不被搜索结果覆盖
    if poi_id in MANUAL_COORDS:
        score -= 50

    return score


def pick_best_place_result(poi: Dict[str, Any], results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not results:
        return None

    ranked = sorted(results, key=lambda item: score_place_result(poi, item), reverse=True)
    best = ranked[0]
    best_score = score_place_result(poi, best)

    # 分数太低，宁可不写，避免把景区外结果写进去
    if best_score < 60:
        return None

    loc = best.get("location") or {}
    lat = loc.get("lat")
    lng = loc.get("lng")
    if lat is None or lng is None:
        return None

    lat = float(lat)
    lng = float(lng)

    if not in_lingshan_bbox(lat, lng):
        return None

    return {
        "lat": lat,
        "lng": lng,
        "matched_title": best.get("title"),
        "matched_address": best.get("address"),
        "source": "tencent_place_search",
        "score": best_score,
    }


def apply_manual_override(poi: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    poi_id = normalize_text(poi.get("poi_id"))
    if poi_id in MANUAL_COORDS:
        lat, lng = MANUAL_COORDS[poi_id]
        poi["lat"] = lat
        poi["lng"] = lng
        poi["coord_source"] = "manual_override"
        poi["coord_matched_title"] = poi.get("name")
        poi["coord_matched_address"] = poi.get("address")
        print(f"[PIN] {poi['name']} -> ({lat}, {lng}) by manual override")
        return poi
    return None


def fill_coords_for_poi(client: TencentMapClient, poi: Dict[str, Any]) -> Dict[str, Any]:
    # 已有合法坐标且在景区内，直接保留
    if poi.get("lat") is not None and poi.get("lng") is not None:
        lat = float(poi["lat"])
        lng = float(poi["lng"])
        if in_lingshan_bbox(lat, lng):
            poi["coord_source"] = poi.get("coord_source") or "existing"
            return poi

    # 核心点位优先使用人工钉点
    pinned = apply_manual_override(poi)
    if pinned:
        return pinned

    queries = build_queries(poi)

    for query in queries:
        try:
            results = client.search_place(keyword=query, region="无锡", page_size=10)
        except Exception as exc:
            print(f"[WARN] search_place failed for {poi.get('name')} | query={query} | {exc}")
            continue

        picked = pick_best_place_result(poi, results)
        if picked:
            poi["lat"] = picked["lat"]
            poi["lng"] = picked["lng"]
            poi["coord_source"] = picked["source"]
            poi["coord_matched_title"] = picked["matched_title"]
            poi["coord_matched_address"] = picked["matched_address"]
            poi["coord_score"] = picked["score"]
            print(f"[OK] {poi['name']} -> ({poi['lat']}, {poi['lng']}) by place search")
            return poi

    poi["coord_source"] = "unresolved"
    print(f"[MISS] {poi.get('name')} still has no safe coordinates")
    return poi


def main() -> None:
    if not INPUT_JSON.exists():
        raise FileNotFoundError(f"Input JSON not found: {INPUT_JSON}")

    settings = get_settings()
    client = TencentMapClient(settings)

    rows = load_json(INPUT_JSON)
    output_rows: List[Dict[str, Any]] = []

    for poi in rows:
        output_rows.append(fill_coords_for_poi(client, dict(poi)))

    save_json(OUTPUT_JSON, output_rows)
    print(f"\nDone. Output saved to: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()

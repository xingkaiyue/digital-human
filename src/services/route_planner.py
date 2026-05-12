from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.schemas import (
    LocationPoint,
    RouteNode,
    RoutePlanData,
    RoutePlanRequest,
    RoutePlanResponse,
    RoutePlanStep,
    RoutePlanSummary,
)


POI_DB: Dict[str, List[dict]] = {
    "lingshan": [
        {
            "poi_id": "LS-GATE",
            "name": "游客中心",
            "aliases": ["游客中心", "入口", "景区入口", "南门入园"],
            "lat": 31.4285,
            "lng": 120.1023,
            "point_type": "service",
            "stay_minutes": 10,
            "intro": "游客中心可领取导览资料、咨询游览路线。",
        },
        {
            "poi_id": "LS-011",
            "name": "灵山大佛",
            "aliases": ["灵山大佛", "大佛"],
            "lat": 31.4297,
            "lng": 120.1058,
            "point_type": "core_spot",
            "stay_minutes": 30,
            "intro": "灵山大佛是景区核心地标，适合重点停留参观。",
        },
    ]
}


def _normalize_repo_poi(raw: Any) -> Optional[dict]:
    if raw is None:
        return None

    if isinstance(raw, dict):
        data = dict(raw)
    else:
        data = {}
        for field in [
            "poi_id",
            "id",
            "name",
            "title",
            "lat",
            "lng",
            "latitude",
            "longitude",
            "point_type",
            "type",
            "poi_type",
            "category",
            "stay_minutes",
            "intro",
            "description",
            "summary",
            "aliases",
        ]:
            if hasattr(raw, field):
                data[field] = getattr(raw, field)

    poi_id = data.get("poi_id") or data.get("id")
    name = data.get("name") or data.get("title")
    lat = data.get("lat") if data.get("lat") is not None else data.get("latitude")
    lng = data.get("lng") if data.get("lng") is not None else data.get("longitude")

    coordinates = data.get("coordinates")
    if isinstance(coordinates, dict):
        lat = lat if lat is not None else coordinates.get("lat") or coordinates.get("latitude")
        lng = lng if lng is not None else coordinates.get("lng") or coordinates.get("longitude")

    if not poi_id or not name or lat is None or lng is None:
        return None

    aliases = data.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [item.strip() for item in re.split(r"[,，/、\s|]+", aliases) if item.strip()]

    return {
        "poi_id": str(poi_id),
        "name": str(name),
        "aliases": aliases,
        "lat": float(lat),
        "lng": float(lng),
        "point_type": data.get("point_type") or data.get("type") or data.get("poi_type") or data.get("category") or "poi",
        "stay_minutes": int(data.get("stay_minutes") or 10),
        "intro": str(data.get("intro") or data.get("description") or data.get("summary") or ""),
        "address": str(data.get("address") or ""),
        "tags": data.get("tags") or [],
    }


def _load_pois_from_repository(scenic_id: str, poi_repository: Any | None) -> List[dict]:
    if poi_repository is None:
        return []

    candidate_methods = ["filter_valid_route_pois", "get_pois", "list_scenic_pois", "load_pois"]
    for method_name in candidate_methods:
        method = getattr(poi_repository, method_name, None)
        if not callable(method):
            continue

        try:
            result = method(scenic_id)
        except TypeError:
            try:
                result = method(scenic_id=scenic_id)
            except Exception:
                continue
        except Exception:
            continue

        rows: List[Any] = []
        if isinstance(result, list):
            rows = result
        elif isinstance(result, dict):
            rows = result.get("pois") or result.get("data") or []

        normalized = [_normalize_repo_poi(item) for item in rows]
        normalized = [item for item in normalized if item]
        if normalized:
            return normalized

    return []


def _load_local_json_pois(scenic_id: str) -> List[dict]:
    file_path = Path(__file__).resolve().parents[1] / "data" / "poi" / f"{scenic_id}.json"
    if not file_path.exists():
        return []
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    rows = payload.get("pois") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []

    normalized = [_normalize_repo_poi(item) for item in rows]
    return [item for item in normalized if item]


def _load_pois_for_scenic(scenic_id: str, poi_repository: Any | None) -> tuple[List[dict], str]:
    repo_pois = _load_pois_from_repository(scenic_id, poi_repository)
    if repo_pois:
        return repo_pois, "repository"

    local_pois = _load_local_json_pois(scenic_id)
    if local_pois:
        return local_pois, "local_json"

    fallback_pois = POI_DB.get(scenic_id, [])
    if fallback_pois:
        return fallback_pois, "hardcoded_fallback"

    return [], "missing"


def _find_poi_by_name_or_id(pois: List[dict], value: Optional[str]) -> Optional[dict]:
    if not value:
        return None
    query = value.strip()
    if not query:
        return None

    for poi in pois:
        if poi["poi_id"] == query or poi["name"] == query:
            return poi

    for poi in pois:
        aliases = poi.get("aliases", []) or []
        if query in aliases:
            return poi

    for poi in pois:
        name = poi["name"]
        aliases = poi.get("aliases", []) or []
        if query in name or name in query:
            return poi
        if any(query in alias or alias in query for alias in aliases):
            return poi
    return None


def _to_route_node(poi: dict) -> RouteNode:
    return RouteNode(
        poi_id=poi["poi_id"],
        name=poi["name"],
        lat=float(poi["lat"]),
        lng=float(poi["lng"]),
        point_type=poi.get("point_type", "poi"),
        stay_minutes=poi.get("stay_minutes"),
        intro=poi.get("intro"),
    )


def _make_current_location_node(point: LocationPoint) -> RouteNode:
    return RouteNode(
        poi_id="CURRENT_LOCATION",
        name="当前位置",
        lat=float(point.lat),
        lng=float(point.lng),
        point_type="current_location",
        stay_minutes=0,
        intro="用户当前位置",
    )


def _mode_text(mode: str) -> str:
    return {"walk": "步行", "drive": "驾车", "bike": "骑行"}.get((mode or "").lower(), "出行")


def _scenic_name(req: RoutePlanRequest) -> str:
    return {"lingshan": "灵山胜境"}.get(req.scenic_id, req.scenic_id)


def _build_arrival_tip(end_node: RouteNode, interests: List[str], family_friendly: bool) -> str:
    parts: List[str] = []
    if end_node.intro:
        parts.append(f"到达后建议先看：{end_node.intro}")
    if interests:
        parts.append(f"结合你的偏好 {'、'.join(interests[:3])}，这里可以适当多停留一会。")
    if family_friendly:
        parts.append("如果是亲子出游，建议先找一个开阔位置稍作停留，再开始讲解和拍照。")
    return "".join(parts)


def _steps_brief(steps: List[RoutePlanStep]) -> str:
    usable = [step for step in steps if (step.instruction or "").strip()]
    if not usable:
        return ""

    chosen = usable[:4]
    sentence_parts: List[str] = []
    for index, step in enumerate(chosen, start=1):
        text = (step.instruction or "").strip("，,。 ")
        if not text:
            continue
        if index == 1:
            sentence_parts.append(f"先{text}")
        elif index == len(chosen):
            sentence_parts.append(f"最后{text}")
        else:
            sentence_parts.append(f"再{text}")
    return "，".join(sentence_parts) + "。"


def _build_narration(
    req: RoutePlanRequest,
    start_node: RouteNode,
    end_node: RouteNode,
    distance_m: int,
    duration_min: int,
    waypoints: List[RouteNode],
    steps: List[RoutePlanStep],
) -> str:
    parts = [
        f"已经为你规划从{start_node.name}前往{end_node.name}的{_mode_text(req.mode)}路线，"
        f"全程大约{distance_m}米，预计{duration_min}分钟。"
    ]
    scenic_name = _scenic_name(req)
    if scenic_name:
        parts.append(f"这段路会逐步进入{scenic_name}的核心游览区域。")
    if waypoints:
        parts.append(f"途中会经过{'、'.join(node.name for node in waypoints)}。")

    step_voice = _steps_brief(steps)
    if step_voice:
        parts.append(step_voice)

    arrival_tip = _build_arrival_tip(end_node=end_node, interests=req.interests, family_friendly=req.family_friendly)
    if arrival_tip:
        parts.append(arrival_tip)
    return "".join(parts)


def _build_guide_answer(
    req: RoutePlanRequest,
    start_node: RouteNode,
    end_node: RouteNode,
    waypoint_nodes: List[RouteNode],
    distance_m: int,
    duration_min: int,
    steps: List[RoutePlanStep],
    actual_mode: str,
    fallback_used: bool = False,
) -> str:
    parts = [f"从{start_node.name}到{end_node.name}，{_mode_text(actual_mode)}全程约{distance_m}米，预计{duration_min}分钟。"]
    if waypoint_nodes:
        parts.append(f"途中经过{'、'.join(node.name for node in waypoint_nodes)}。")
    if steps:
        step_summary = "；".join(
            f"{step.instruction}（约{step.distance_m}米）"
            for step in steps[:4]
            if (step.instruction or "").strip()
        )
        if step_summary:
            parts.append(f"主要路线为：{step_summary}。")
    if end_node.intro:
        parts.append(f"到达后可重点关注：{end_node.intro}")
    if fallback_used:
        parts.append("当前点位信息来自基础路线兜底数据。")
    return "".join(parts)


def build_route_plan(
    req: RoutePlanRequest,
    tencent_map_client: Any,
    poi_repository: Any | None = None,
) -> RoutePlanResponse:
    pois, poi_source = _load_pois_for_scenic(req.scenic_id, poi_repository)
    if not pois:
        raise ValueError(f"Unsupported scenic_id: {req.scenic_id}")

    start_poi = _find_poi_by_name_or_id(pois, req.start_poi)
    end_poi = _find_poi_by_name_or_id(pois, req.end_poi)
    if not end_poi:
        raise ValueError("无法识别终点 end_poi，请传景点名称或已知 poi_id")

    waypoint_pois: List[dict] = []
    for waypoint in req.waypoints:
        poi = _find_poi_by_name_or_id(pois, waypoint)
        if poi and poi["poi_id"] != end_poi["poi_id"] and not any(item["poi_id"] == poi["poi_id"] for item in waypoint_pois):
            waypoint_pois.append(poi)

    if start_poi:
        start_node = _to_route_node(start_poi)
    elif req.current_location is not None:
        start_node = _make_current_location_node(req.current_location)
    else:
        raise ValueError("start_poi 和 current_location 至少需要提供一个")

    end_node = _to_route_node(end_poi)
    waypoint_nodes = [_to_route_node(poi) for poi in waypoint_pois]

    planned = tencent_map_client.plan_route(
        start=start_node.model_dump(),
        end=end_node.model_dump(),
        waypoints=[node.model_dump() for node in waypoint_nodes],
        mode=req.mode,
    )

    total_distance_m = int(planned.get("distance_m", 0) or 0)
    steps = [
        RoutePlanStep(
            seq_no=int(item.get("seq_no", index)),
            instruction=item.get("instruction", "") or "继续前行",
            distance_m=int(item.get("distance_m", 0) or 0),
            duration_min=int(item.get("duration_min", 0) or 0),
        )
        for index, item in enumerate(planned.get("steps", []), start=1)
    ]

    step_total_duration_min = sum(step.duration_min for step in steps)
    total_duration_min = max(int(planned.get("duration_min", 0) or 0), step_total_duration_min)
    route_nodes = [start_node, *waypoint_nodes, end_node]

    narration = _build_narration(
        req=req,
        start_node=start_node,
        end_node=end_node,
        distance_m=total_distance_m,
        duration_min=total_duration_min,
        waypoints=waypoint_nodes,
        steps=steps,
    )
    guide_answer = _build_guide_answer(
        req=req,
        start_node=start_node,
        end_node=end_node,
        waypoint_nodes=waypoint_nodes,
        distance_m=total_distance_m,
        duration_min=total_duration_min,
        steps=steps,
        actual_mode=req.mode,
        fallback_used=(poi_source != "repository"),
    )
    arrival_tip = _build_arrival_tip(end_node=end_node, interests=req.interests, family_friendly=req.family_friendly)
    polyline_points = [LocationPoint(**point) for point in planned.get("polyline", [])]

    return RoutePlanResponse(
        message=f"已为你规划从{start_node.name}到{end_node.name}的路线",
        data=RoutePlanData(
            scenic_id=req.scenic_id,
            start=start_node,
            end=end_node,
            waypoints=waypoint_nodes,
            route_nodes=route_nodes,
            polyline=polyline_points,
            steps=steps,
            summary=RoutePlanSummary(
                total_distance_m=total_distance_m,
                total_duration_min=total_duration_min,
                mode=req.mode,
            ),
            narration=narration,
            guide_answer=guide_answer,
            arrival_tip=arrival_tip,
            map_pois=route_nodes,
            debug={
                **planned.get("debug", {}),
                "poi_source": poi_source,
                "poi_count": len(pois),
            },
        ),
        ui_command={
            "type": "display_route",
            "mode": req.mode,
            "scenic_id": req.scenic_id,
            "route_nodes": [node.model_dump() for node in route_nodes],
            "polyline": [point.model_dump() for point in polyline_points],
            "summary": {
                "total_distance_m": total_distance_m,
                "total_duration_min": total_duration_min,
                "mode": req.mode,
            },
            "speech_text": guide_answer,
            "arrival_tip": arrival_tip,
        },
    )

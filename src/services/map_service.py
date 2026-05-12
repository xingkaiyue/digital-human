from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class RoutePoint:
    poi_id: str
    name: str
    lat: float
    lng: float
    point_type: str  # start / waypoint / end / explain
    stay_minutes: Optional[int] = None
    intro: Optional[str] = None


@dataclass
class RouteStep:
    instruction: str
    distance_m: Optional[int] = None
    duration_min: Optional[int] = None


@dataclass
class RouteResult:
    success: bool
    route_type: str
    distance_m: int
    duration_min: int
    start_name: str
    end_name: str
    steps: List[RouteStep]
    points: List[RoutePoint]
    polyline: List[List[float]]
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "route_type": self.route_type,
            "distance_m": self.distance_m,
            "duration_min": self.duration_min,
            "start_name": self.start_name,
            "end_name": self.end_name,
            "steps": [asdict(x) for x in self.steps],
            "points": [asdict(x) for x in self.points],
            "polyline": self.polyline,
            "error_message": self.error_message,
        }


class MapService:
    """
    地图能力封装层
    现在你可以先接腾讯地图 / 高德 / 自己的景区 GIS
    对上层统一输出 RouteResult
    """

    def __init__(self, map_client: Any) -> None:
        self.map_client = map_client

    def plan_route(
        self,
        start: Dict[str, Any],
        end: Dict[str, Any],
        waypoints: Optional[List[Dict[str, Any]]] = None,
        mode: str = "walk",
    ) -> RouteResult:
        waypoints = waypoints or []

        try:
            # 这里按你真实地图 SDK 改
            raw = self.map_client.plan_route(
                start=start,
                end=end,
                waypoints=waypoints,
                mode=mode,
            )

            return self._parse_route_result(raw, start, end, mode)

        except Exception as exc:
            return RouteResult(
                success=False,
                route_type=mode,
                distance_m=0,
                duration_min=0,
                start_name=start.get("name", "当前位置"),
                end_name=end.get("name", "目的地"),
                steps=[RouteStep(instruction="地图路线规划失败，请稍后重试。")],
                points=[],
                polyline=[],
                error_message=str(exc),
            )

    def _parse_route_result(
        self,
        raw: Dict[str, Any],
        start: Dict[str, Any],
        end: Dict[str, Any],
        mode: str,
    ) -> RouteResult:
        steps: List[RouteStep] = []
        for item in raw.get("steps", []):
            steps.append(
                RouteStep(
                    instruction=item.get("instruction", ""),
                    distance_m=item.get("distance_m"),
                    duration_min=item.get("duration_min"),
                )
            )

        points: List[RoutePoint] = [
            RoutePoint(
                poi_id=start.get("poi_id", "start"),
                name=start.get("name", "当前位置"),
                lat=float(start["lat"]),
                lng=float(start["lng"]),
                point_type="start",
            ),
            RoutePoint(
                poi_id=end.get("poi_id", "end"),
                name=end.get("name", "目的地"),
                lat=float(end["lat"]),
                lng=float(end["lng"]),
                point_type="end",
            ),
        ]

        for wp in raw.get("waypoints", []):
            points.insert(
                -1,
                RoutePoint(
                    poi_id=wp.get("poi_id", ""),
                    name=wp.get("name", ""),
                    lat=float(wp["lat"]),
                    lng=float(wp["lng"]),
                    point_type=wp.get("point_type", "waypoint"),
                    stay_minutes=wp.get("stay_minutes"),
                    intro=wp.get("intro"),
                ),
            )

        return RouteResult(
            success=True,
            route_type=mode,
            distance_m=int(raw.get("distance_m", 0)),
            duration_min=int(raw.get("duration_min", 0)),
            start_name=start.get("name", "当前位置"),
            end_name=end.get("name", "目的地"),
            steps=steps,
            points=points,
            polyline=raw.get("polyline", []),
        )

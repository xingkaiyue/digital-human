from __future__ import annotations

from math import radians, sin, cos, sqrt, atan2
from typing import List, Optional

from .repository import POIRepository
from .schema import POIRecord


class POISearchService:
    def __init__(self, repository: POIRepository):
        self.repository = repository

    def search_by_name(self, keyword: str, scenic_name: Optional[str] = None, limit: int = 10) -> List[POIRecord]:
        return self.repository.search_by_name(keyword=keyword, scenic_name=scenic_name, limit=limit)

    def nearby(
        self,
        scenic_name: str,
        lat: float,
        lng: float,
        limit: int = 10,
    ) -> List[POIRecord]:
        items = self.repository.list_by_scenic(scenic_name=scenic_name, limit=500)
        valid_items = [x for x in items if x.lat is not None and x.lng is not None]
        valid_items.sort(key=lambda x: self._distance(lat, lng, x.lat, x.lng))
        return valid_items[:limit]

    @staticmethod
    def _distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        r = 6371.0
        dlat = radians(lat2 - lat1)
        dlng = radians(lng2 - lng1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return r * c

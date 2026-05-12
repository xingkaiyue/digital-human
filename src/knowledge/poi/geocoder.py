from __future__ import annotations

from typing import List

from .schema import POIRecord


class POIGeocoder:
    def __init__(self, tencent_map_client):
        self.tencent_map_client = tencent_map_client

    def geocode_many(self, records: List[POIRecord]) -> List[POIRecord]:
        result = []
        for item in records:
            if item.lat is not None and item.lng is not None:
                result.append(item)
                continue

            queries = self._build_queries(item)
            geocoded = False

            for query in queries:
                try:
                    geo = self.tencent_map_client.geocode(query)
                except Exception:
                    continue

                if not geo:
                    continue

                item.lat = geo.get("lat")
                item.lng = geo.get("lng")
                item.geocode_source = query
                item.geocode_confidence = float(geo.get("confidence", 0.0))
                geocoded = True
                break

            if not geocoded:
                item.geocode_source = None
                item.geocode_confidence = 0.0

            result.append(item)
        return result

    @staticmethod
    def _build_queries(item: POIRecord) -> List[str]:
        queries = []
        if item.address and item.scenic_name:
            queries.append(f"{item.scenic_name}{item.address}")
        if item.name and item.scenic_name:
            queries.append(f"{item.scenic_name}{item.name}")
        if item.address:
            queries.append(item.address)
        if item.name:
            queries.append(item.name)
        return queries

from __future__ import annotations

from typing import Dict

from .extractor import POIExtractor
from .geocoder import POIGeocoder
from .repository import POIRepository


class POIIngestService:
    def __init__(
        self,
        extractor: POIExtractor,
        geocoder: POIGeocoder,
        repository: POIRepository,
    ):
        self.extractor = extractor
        self.geocoder = geocoder
        self.repository = repository

    def ingest_file(self, file_path: str) -> Dict:
        records = self.extractor.extract(file_path)
        total_extracted = len(records)

        records = self.geocoder.geocode_many(records)
        total_geocoded = sum(1 for x in records if x.lat is not None and x.lng is not None)

        total_saved = self.repository.upsert_many(records)

        return {
            "success": True,
            "file_path": file_path,
            "total_extracted": total_extracted,
            "total_geocoded": total_geocoded,
            "total_saved": total_saved,
        }

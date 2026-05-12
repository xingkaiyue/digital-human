from __future__ import annotations


class POIAdminService:
    def __init__(self, ingest_service):
        self.ingest_service = ingest_service

    def import_poi_file(self, file_path: str) -> dict:
        return self.ingest_service.ingest_file(file_path=file_path)

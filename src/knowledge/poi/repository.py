from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, List, Optional

from .schema import POIRecord


class POIRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pois (
                    poi_id TEXT PRIMARY KEY,
                    scenic_id TEXT,
                    scenic_name TEXT,
                    name TEXT NOT NULL,
                    aliases TEXT,
                    category TEXT,
                    address TEXT,
                    description TEXT,
                    tags TEXT,
                    lat REAL,
                    lng REAL,
                    geocode_source TEXT,
                    geocode_confidence REAL,
                    source_file TEXT,
                    source_row_no INTEGER,
                    status TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pois_name ON pois(name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pois_scenic_id ON pois(scenic_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pois_scenic_name ON pois(scenic_name)")

    def upsert_many(self, records: List[POIRecord]) -> int:
        with self._get_conn() as conn:
            for item in records:
                conn.execute(
                    """
                    INSERT INTO pois (
                        poi_id, scenic_id, scenic_name, name, aliases, category,
                        address, description, tags, lat, lng,
                        geocode_source, geocode_confidence,
                        source_file, source_row_no, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(poi_id) DO UPDATE SET
                        scenic_id=excluded.scenic_id,
                        scenic_name=excluded.scenic_name,
                        name=excluded.name,
                        aliases=excluded.aliases,
                        category=excluded.category,
                        address=excluded.address,
                        description=excluded.description,
                        tags=excluded.tags,
                        lat=excluded.lat,
                        lng=excluded.lng,
                        geocode_source=excluded.geocode_source,
                        geocode_confidence=excluded.geocode_confidence,
                        source_file=excluded.source_file,
                        source_row_no=excluded.source_row_no,
                        status=excluded.status
                    """,
                    (
                        item.poi_id,
                        item.scenic_id,
                        item.scenic_name,
                        item.name,
                        json.dumps(item.aliases, ensure_ascii=False),
                        item.category,
                        item.address,
                        item.description,
                        json.dumps(item.tags, ensure_ascii=False),
                        item.lat,
                        item.lng,
                        item.geocode_source,
                        item.geocode_confidence,
                        item.source_file,
                        item.source_row_no,
                        item.status,
                    ),
                )
        return len(records)

    def import_json(self, json_path: str) -> int:
        rows = json.loads(Path(json_path).read_text(encoding="utf-8"))
        records: List[POIRecord] = []

        for row in rows:
            records.append(
                POIRecord(
                    poi_id=row["poi_id"],
                    scenic_id=row.get("scenic_id") or "lingshan",
                    scenic_name=row.get("scenic_name") or "灵山胜境",
                    name=row["name"],
                    aliases=row.get("aliases", []),
                    category=row.get("category"),
                    address=row.get("address"),
                    description=row.get("description"),
                    tags=row.get("tags", []),
                    lat=row.get("lat"),
                    lng=row.get("lng"),
                    geocode_source=row.get("geocode_source"),
                    geocode_confidence=row.get("geocode_confidence"),
                    source_file=row.get("source_file"),
                    source_row_no=row.get("source_row_no"),
                    status=row.get("status", "active"),
                )
            )

        return self.upsert_many(records)

    def search_by_name(
        self,
        keyword: str,
        scenic_name: Optional[str] = None,
        scenic_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[POIRecord]:
        sql = "SELECT * FROM pois WHERE status='active' AND (name LIKE ? OR aliases LIKE ?)"
        params: List[Any] = [f"%{keyword}%", f"%{keyword}%"]

        if scenic_id:
            sql += " AND scenic_id = ?"
            params.append(scenic_id)
        elif scenic_name:
            sql += " AND scenic_name = ?"
            params.append(scenic_name)

        sql += " LIMIT ?"
        params.append(limit)

        with self._get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_by_id(self, poi_id: str) -> Optional[POIRecord]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM pois WHERE poi_id = ?", (poi_id,)).fetchone()
        return self._row_to_record(row) if row else None

    def list_by_scenic(
        self,
        scenic_name: Optional[str] = None,
        scenic_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[POIRecord]:
        if scenic_id:
            sql = "SELECT * FROM pois WHERE status='active' AND scenic_id = ? LIMIT ?"
            params = (scenic_id, limit)
        else:
            sql = "SELECT * FROM pois WHERE status='active' AND scenic_name = ? LIMIT ?"
            params = (scenic_name, limit)

        with self._get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_pois_by_scenic_id(self, scenic_id: str, limit: int = 500) -> List[dict]:
        return [self._record_to_dict(x) for x in self.list_by_scenic(scenic_id=scenic_id, limit=limit)]

    def get_pois_by_scenic_id(self, scenic_id: str, limit: int = 500) -> List[dict]:
        return self.list_pois_by_scenic_id(scenic_id=scenic_id, limit=limit)

    def list_pois(
        self,
        scenic_id: Optional[str] = None,
        scenic_name: Optional[str] = None,
        limit: int = 500,
    ) -> List[dict]:
        return [
            self._record_to_dict(x)
            for x in self.list_by_scenic(scenic_id=scenic_id, scenic_name=scenic_name, limit=limit)
        ]

    def get_pois(
        self,
        scenic_id: Optional[str] = None,
        scenic_name: Optional[str] = None,
        limit: int = 500,
    ) -> List[dict]:
        return self.list_pois(scenic_id=scenic_id, scenic_name=scenic_name, limit=limit)

    def load_pois(
        self,
        scenic_id: Optional[str] = None,
        scenic_name: Optional[str] = None,
        limit: int = 500,
    ) -> List[dict]:
        return self.list_pois(scenic_id=scenic_id, scenic_name=scenic_name, limit=limit)

    @staticmethod
    def _record_to_dict(item: POIRecord) -> dict:
        return {
            "poi_id": item.poi_id,
            "id": item.poi_id,
            "scenic_id": item.scenic_id,
            "scenic_name": item.scenic_name,
            "name": item.name,
            "title": item.name,
            "aliases": item.aliases or [],
            "category": item.category,
            "type": item.category or "poi",
            "address": item.address,
            "description": item.description,
            "summary": item.description,
            "tags": item.tags or [],
            "lat": item.lat,
            "lng": item.lng,
            "latitude": item.lat,
            "longitude": item.lng,
            "status": item.status,
            "source_file": item.source_file,
            "source_row_no": item.source_row_no,
        }

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> POIRecord:
        return POIRecord(
            poi_id=row["poi_id"],
            scenic_id=row["scenic_id"],
            scenic_name=row["scenic_name"],
            name=row["name"],
            aliases=json.loads(row["aliases"] or "[]"),
            category=row["category"],
            address=row["address"],
            description=row["description"],
            tags=json.loads(row["tags"] or "[]"),
            lat=row["lat"],
            lng=row["lng"],
            geocode_source=row["geocode_source"],
            geocode_confidence=row["geocode_confidence"],
            source_file=row["source_file"],
            source_row_no=row["source_row_no"],
            status=row["status"],
        )

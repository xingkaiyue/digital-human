from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class ScenicRegistryLoader:
    def __init__(self, registry_path: Optional[str] = None):
        if registry_path is None:
            registry_path = str(Path(__file__).resolve().parent / "scenic_registry.json")
        self.registry_path = Path(registry_path)
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.registry_path.exists():
            raise FileNotFoundError(f"景区配置文件不存在: {self.registry_path}")
        with self.registry_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @property
    def data(self) -> Dict[str, Any]:
        return self._data

    def list_destinations(self) -> List[Dict[str, Any]]:
        return self._data.get("destinations", []) or []

    def match_destination(self, name: str) -> Optional[Dict[str, Any]]:
        name = (name or "").strip()
        if not name:
            return None

        for destination in self.list_destinations():
            if destination.get("destination_name") == name:
                return destination

            aliases = destination.get("aliases", []) or []
            if name in aliases:
                return destination

        return None

    def match_scenic(self, scenic_name: str) -> Optional[Dict[str, Any]]:
        scenic_name = (scenic_name or "").strip()
        if not scenic_name:
            return None

        for destination in self.list_destinations():
            for scenic in destination.get("scenics", []) or []:
                if scenic.get("scenic_name") == scenic_name:
                    return {
                        "destination_id": destination.get("destination_id"),
                        "destination_name": destination.get("destination_name"),
                        "scenic_id": scenic.get("scenic_id"),
                        "scenic_name": scenic.get("scenic_name"),
                        "doc_types": scenic.get("doc_types", []),
                    }

                aliases = scenic.get("aliases", []) or []
                if scenic_name in aliases:
                    return {
                        "destination_id": destination.get("destination_id"),
                        "destination_name": destination.get("destination_name"),
                        "scenic_id": scenic.get("scenic_id"),
                        "scenic_name": scenic.get("scenic_name"),
                        "doc_types": scenic.get("doc_types", []),
                    }

        return None

    def get_scenic_by_ids(
        self,
        destination_id: Optional[str],
        scenic_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        if not destination_id or not scenic_id:
            return None

        for destination in self.list_destinations():
            if destination.get("destination_id") != destination_id:
                continue

            for scenic in destination.get("scenics", []) or []:
                if scenic.get("scenic_id") == scenic_id:
                    return {
                        "destination_id": destination.get("destination_id"),
                        "destination_name": destination.get("destination_name"),
                        "scenic_id": scenic.get("scenic_id"),
                        "scenic_name": scenic.get("scenic_name"),
                        "doc_types": scenic.get("doc_types", []),
                    }

        return None

    def resolve_scene_context(
        self,
        destination_id: Optional[str] = None,
        destination_name: Optional[str] = None,
        scenic_id: Optional[str] = None,
        scenic_name: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        if scenic_name:
            scenic = self.match_scenic(scenic_name)
            if scenic:
                return scenic

        if destination_id and scenic_id:
            scenic = self.get_scenic_by_ids(destination_id, scenic_id)
            if scenic:
                return scenic

        if destination_name:
            destination = self.match_destination(destination_name)
            if destination and not scenic_id and not scenic_name:
                return {
                    "destination_id": destination.get("destination_id"),
                    "destination_name": destination.get("destination_name"),
                    "scenic_id": None,
                    "scenic_name": None,
                }

        return {
            "destination_id": destination_id,
            "destination_name": destination_name,
            "scenic_id": scenic_id,
            "scenic_name": scenic_name,
        }

from __future__ import annotations

from typing import Dict, Optional

from config.scenic_registry_loader import ScenicRegistryLoader


_loader = ScenicRegistryLoader()


def match_scenic(scenic_name: str) -> Optional[Dict]:
    return _loader.match_scenic(scenic_name)


def match_destination(destination_name: str) -> Optional[Dict]:
    return _loader.match_destination(destination_name)


def resolve_scene_context(
    destination_id: Optional[str] = None,
    destination_name: Optional[str] = None,
    scenic_id: Optional[str] = None,
    scenic_name: Optional[str] = None,
) -> Dict:
    return _loader.resolve_scene_context(
        destination_id=destination_id,
        destination_name=destination_name,
        scenic_id=scenic_id,
        scenic_name=scenic_name,
    )

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class POIRecord:
    poi_id: str
    scenic_id: Optional[str] = None
    scenic_name: Optional[str] = None

    name: str = ""
    aliases: List[str] = field(default_factory=list)
    category: Optional[str] = None

    address: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    lat: Optional[float] = None
    lng: Optional[float] = None
    geocode_source: Optional[str] = None
    geocode_confidence: Optional[float] = None

    source_file: Optional[str] = None
    source_row_no: Optional[int] = None
    status: str = "active"

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SceneContext:
    # 大景区 / 景区群
    destination_id: str
    destination_name: str

    # 当前具体子景区
    scenic_id: Optional[str] = None
    scenic_name: Optional[str] = None

    # current_only: 只查当前子景区
    # destination_all: 查整个大景区
    scope_mode: str = "current_only"

    def resolve_filter_scenic_id(self) -> Optional[str]:
        if self.scope_mode == "current_only":
            return self.scenic_id
        return None

    def resolve_filter_destination_id(self) -> Optional[str]:
        if self.scope_mode == "destination_all":
            return self.destination_id
        return None

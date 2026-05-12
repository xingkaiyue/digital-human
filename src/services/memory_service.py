from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from api.schemas import ConversationMemory, MemoryTurn


class ConversationMemoryService:
    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = Path(storage_dir or Path("src/data/memory"))
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, session_id: str) -> Path:
        safe_session_id = re.sub(r"[^0-9A-Za-z_\-]", "_", (session_id or "").strip())
        if not safe_session_id:
            raise ValueError("session_id 不能为空")
        return self.storage_dir / f"{safe_session_id}.json"

    def get_memory(self, session_id: str) -> ConversationMemory:
        file_path = self._file_path(session_id)
        if not file_path.exists():
            return ConversationMemory(session_id=session_id)

        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return ConversationMemory(session_id=session_id)

        payload.setdefault("session_id", session_id)
        payload.setdefault("turns", [])
        payload.setdefault("profile", {})
        payload.setdefault("last_route", {})
        payload.setdefault("summary", "")
        payload.setdefault("last_intent", "")
        payload.setdefault("last_poi", None)

        return ConversationMemory(**payload)

    def save_memory(self, memory: ConversationMemory) -> None:
        file_path = self._file_path(memory.session_id)
        file_path.write_text(
            json.dumps(memory.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def update_from_turn(
        self,
        session_id: str,
        query: str,
        response: dict,
        user_profile: dict | None = None,
    ) -> ConversationMemory:
        memory = self.get_memory(session_id)
        response = response or {}

        if user_profile:
            merged_profile = dict(memory.profile)
            merged_profile.update(user_profile)
            memory.profile = self._normalize_profile(merged_profile)

        intent = str(response.get("intent") or "")
        action = str(response.get("action") or "")
        answer = str(response.get("answer") or response.get("speech_text") or "")

        memory.turns.append(
            MemoryTurn(
                query=query,
                intent=intent,
                answer=answer,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )
        memory.turns = memory.turns[-20:]
        memory.last_intent = intent

        data = response.get("data") or {}

        if intent in {"spot_explain", "knowledge_qa"}:
            memory.last_poi = (
                data.get("spot_name")
                or data.get("last_poi")
                or memory.last_poi
            )

        if intent == "route_plan":
            self._update_route_memory(memory=memory, data=data, action=action)

        if intent == "nearby_search":
            center = data.get("center") or {}
            memory.last_poi = center.get("name") or memory.last_poi

        memory.summary = self._build_summary(memory.profile)
        self.save_memory(memory)
        return memory

    def _update_route_memory(
        self,
        memory: ConversationMemory,
        data: Dict[str, Any],
        action: str = "",
    ) -> None:
        old_route = dict(memory.last_route or {})

        # 路线追问返回的 data 里通常有 last_route。
        # 这种情况下只保留旧路线，不要把 start_poi / end_poi 覆盖成 None。
        if data.get("last_route"):
            last_route = data.get("last_route") or {}
            if isinstance(last_route, dict):
                merged = dict(old_route)
                for key, value in last_route.items():
                    if value not in [None, "", {}]:
                        merged[key] = value
                memory.last_route = merged
            return

        start_name = self._extract_route_name(data.get("start"))
        end_name = self._extract_route_name(data.get("end"))
        summary = data.get("summary") or {}

        # 真正路线规划结果：有 start/end/summary，可以更新 last_route
        if start_name or end_name or summary:
            memory.last_route = {
                "start_poi": start_name or old_route.get("start_poi"),
                "end_poi": end_name or old_route.get("end_poi"),
                "mode": data.get("mode")
                or summary.get("mode")
                or old_route.get("mode")
                or "walk",
                "summary": summary or old_route.get("summary") or {},
            }

            memory.last_poi = end_name or memory.last_poi
            return

        # route_plan 但没有任何路线数据，保持旧记忆
        memory.last_route = old_route

    def build_context(self, session_id: str) -> dict:
        memory = self.get_memory(session_id)
        return memory.model_dump()

    def clear_memory(self, session_id: str) -> None:
        file_path = self._file_path(session_id)
        if file_path.exists():
            file_path.unlink()

    @staticmethod
    def _extract_route_name(raw: Any) -> str | None:
        if isinstance(raw, dict):
            return raw.get("name")
        return None

    @staticmethod
    def _normalize_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(profile)

        interests = normalized.get("interests") or []
        if isinstance(interests, str):
            interests = [
                item.strip()
                for item in re.split(r"[,，/、\s]+", interests)
                if item.strip()
            ]

        normalized["interests"] = list(
            dict.fromkeys(
                str(item).strip()
                for item in interests
                if str(item).strip()
            )
        )

        return normalized

    @staticmethod
    def _build_summary(profile: Dict[str, Any]) -> str:
        if not profile:
            return ""

        parts = []

        travel_type = profile.get("travel_type")
        if travel_type == "family" or profile.get("family_friendly"):
            parts.append("用户是亲子游客")

        pace = profile.get("pace")
        if pace == "slow":
            parts.append("步行节奏偏慢")

        if profile.get("avoid_long_walk"):
            parts.append("希望少走路")

        interests = profile.get("interests") or []
        if interests:
            parts.append(f"偏好{','.join(interests)}")

        answer_style = profile.get("answer_style")
        if answer_style:
            parts.append(f"回答风格偏{answer_style}")

        return "，".join(parts)

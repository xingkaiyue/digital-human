from __future__ import annotations

import re
from typing import Any, Dict, Optional

from knowledge.scene_context import SceneContext
from modules.intent_parser import IntentParser


class ModelRouter:
    def __init__(
        self,
        llm_aggregator=None,
        vector_retriever=None,
        tencent_map_client=None,
        xunfei_tts=None,
        knowledge_service=None,
        route_backend_client=None,
    ):
        self.llm_aggregator = llm_aggregator
        self.vector_retriever = vector_retriever
        self.tencent_map_client = tencent_map_client
        self.xunfei_tts = xunfei_tts
        self.knowledge_service = knowledge_service
        self.route_backend_client = route_backend_client
        self.intent_parser = IntentParser()

    def handle(
        self,
        query: str,
        scene_context: dict | SceneContext | None = None,
        user_profile: Optional[dict] = None,
    ) -> dict:
        scene = self._normalize_scene_context(scene_context)
        parsed = self.intent_parser.parse(query)

        # 先加一层更强的路线兜底识别，避免“怎么走/带我去”被落到知识问答
        route_slots = self._try_parse_route_query(query)
        if route_slots is not None:
            return self._response(
                intent="route_plan",
                action="guide_route_plan",
                speech_text=route_slots["speech_text"],
                ui_command={
                    "type": "request_route_plan",
                    "query": query,
                    "start_poi": route_slots.get("start_poi"),
                    "end_poi": route_slots.get("end_poi"),
                    "mode": "walk",
                },
                data={
                    "query": query,
                    "start_poi": route_slots.get("start_poi"),
                    "end_poi": route_slots.get("end_poi"),
                    "mode": "walk",
                    "scenic_id": self._ctx_get(scene, "scenic_id"),
                    "scenic_name": self._ctx_get(scene, "scenic_name"),
                },
            )

        if parsed.intent == "greeting":
            return self._response(
                intent=parsed.intent,
                action="speak",
                speech_text="你好，我是你的景区导游助手。你可以问我景点、路线，或者直接让我打开地图页、推荐页。",
            )

        if parsed.intent == "thanks":
            return self._response(
                intent=parsed.intent,
                action="speak",
                speech_text="不客气，祝你游玩愉快。",
            )

        if parsed.intent == "ui_show_avatar":
            return self._response(
                intent=parsed.intent,
                action="show_avatar",
                speech_text="好的，我来了。",
                ui_command={"type": "show_avatar"},
            )

        if parsed.intent == "ui_hide_avatar":
            return self._response(
                intent=parsed.intent,
                action="hide_avatar",
                speech_text="好的，我先隐藏，有需要再叫我。",
                ui_command={"type": "hide_avatar"},
            )

        if parsed.intent == "ui_navigate_page":
            target_page = parsed.slots.get("target_page", "current")
            return self._response(
                intent=parsed.intent,
                action="navigate_page",
                speech_text=f"好的，带你去{self._page_name(target_page)}。",
                ui_command={"type": "navigate", "page": target_page},
                data={"target_page": target_page},
            )

        if parsed.intent == "ui_close_page":
            target_page = parsed.slots.get("target_page", "current")
            return self._response(
                intent=parsed.intent,
                action="close_page",
                speech_text="好的，已为你关闭当前页面。" if target_page == "current" else f"好的，已关闭{self._page_name(target_page)}。",
                ui_command={"type": "close", "page": target_page},
                data={"target_page": target_page},
            )

        if parsed.intent == "ui_page_intro":
            target_page = parsed.slots.get("target_page", "current")
            return self._response(
                intent=parsed.intent,
                action="page_intro",
                speech_text=self._build_page_intro(target_page),
                ui_command={"type": "none"},
                data={"target_page": target_page},
            )

        if parsed.intent in {"spot_list", "spot_recommend", "spot_explain", "unknown"}:
            if self.knowledge_service is None:
                return self._response(
                    intent=parsed.intent,
                    action="speak",
                    speech_text="当前知识服务不可用。",
                )

            rag_answer = self.knowledge_service.answer(
                question=query,
                scene_context=scene,
            )
            return self._response(
                intent=parsed.intent,
                action="rag_answer",
                speech_text=rag_answer.answer,
                data={
                    "question": rag_answer.question,
                    "model": rag_answer.model,
                    "retrieved_contexts": [
                        {
                            "text": item.text,
                            "metadata": item.metadata,
                            "distance": item.distance,
                            "score": item.score,
                        }
                        for item in rag_answer.contexts
                    ],
                },
            )

        if parsed.intent in {"route_plan", "navigation_route"}:
            return self._response(
                intent="route_plan",
                action="guide_route_plan",
                speech_text="我来帮你规划路线，请告诉我起点和终点，比如从游客中心到灵山大佛怎么走。",
                ui_command={"type": "request_route_plan", "query": query, "mode": "walk"},
                data={
                    "query": query,
                    "scenic_id": self._ctx_get(scene, "scenic_id"),
                    "scenic_name": self._ctx_get(scene, "scenic_name"),
                },
            )

        return self._response(
            intent="unknown",
            action="speak",
            speech_text="我理解得还不够准确，你可以再说具体一点。",
        )

    def handle_ui_event(
        self,
        event_type: str,
        page_id: str,
        scene_context: dict | SceneContext | None = None,
        user_profile: Optional[dict] = None,
    ) -> dict:
        _ = self._normalize_scene_context(scene_context)

        if event_type == "page_enter":
            return self._response(
                intent="page_enter",
                action="show_avatar_and_speak",
                speech_text=self._build_page_intro(page_id),
                ui_command={"type": "show_avatar"},
                data={"page_id": page_id},
            )

        return self._response(
            intent="unknown_event",
            action="none",
            speech_text="",
            ui_command={"type": "none"},
            data={"event_type": event_type, "page_id": page_id},
        )

    def _try_parse_route_query(self, query: str) -> Optional[Dict[str, Any]]:
        text = (query or "").strip()
        if not text:
            return None

        route_keywords = [
            "怎么走",
            "怎么去",
            "带我去",
            "去哪里",
            "路线",
            "导航",
            "从",
            "到",
            "多久",
            "多远",
            "最近的卫生间",
            "最近厕所",
            "最近洗手间",
        ]
        if not any(k in text for k in route_keywords):
            return None

        # 特判“最近的卫生间”
        if any(k in text for k in ["最近的卫生间", "最近厕所", "最近洗手间"]):
            return {
                "start_poi": None,
                "end_poi": "游客中心卫生间",
                "speech_text": "好的，我来帮你规划去最近卫生间的路线。",
            }

        patterns = [
            r"从(?P<start>.+?)到(?P<end>.+?)(怎么走|怎么去|多久|多远)$",
            r"从(?P<start>.+?)去(?P<end>.+?)(怎么走|怎么去|多久|多远)$",
            r"带我去(?P<end>.+)$",
            r"去(?P<end>.+?)(怎么走|怎么去|多久|多远)$",
        ]

        for pattern in patterns:
            m = re.search(pattern, text)
            if not m:
                continue

            start_poi = m.groupdict().get("start")
            end_poi = m.groupdict().get("end")

            if end_poi:
                end_poi = end_poi.strip("，。？? ")

            if start_poi:
                start_poi = start_poi.strip("，。？? ")

            if end_poi:
                if start_poi:
                    speech = f"好的，我来帮你规划从{start_poi}到{end_poi}的路线。"
                else:
                    speech = f"好的，我来帮你规划去{end_poi}的路线。"
                return {
                    "start_poi": start_poi,
                    "end_poi": end_poi,
                    "speech_text": speech,
                }

        return {
            "start_poi": None,
            "end_poi": None,
            "speech_text": "我识别到你在问路线，请告诉我起点和终点。",
        }

    def _normalize_scene_context(self, scene_context: dict | SceneContext | None) -> SceneContext | None:
        if scene_context is None:
            return None
        if isinstance(scene_context, SceneContext):
            return scene_context
        return SceneContext(
            destination_id=scene_context.get("destination_id"),
            destination_name=scene_context.get("destination_name"),
            scenic_id=scene_context.get("scenic_id"),
            scenic_name=scene_context.get("scenic_name"),
            scope_mode=scene_context.get("scope_mode", "current_only"),
        )

    @staticmethod
    def _ctx_get(scene_context: dict | SceneContext | None, key: str) -> Any:
        if scene_context is None:
            return None
        if isinstance(scene_context, dict):
            return scene_context.get(key)
        return getattr(scene_context, key, None)

    @staticmethod
    def _response(
        intent: str,
        action: str,
        speech_text: str,
        ui_command: Optional[dict] = None,
        data: Optional[dict] = None,
    ) -> dict:
        return {
            "intent": intent,
            "action": action,
            "speech_text": speech_text,
            "ui_command": ui_command or {"type": "none"},
            "data": data or {},
        }

    @staticmethod
    def _page_name(page_id: str) -> str:
        mapping = {
            "home": "首页",
            "map": "地图页",
            "recommend": "推荐页",
            "route": "路线页",
            "scenic_detail": "景点详情页",
            "profile": "个人中心",
            "current": "当前页面",
        }
        return mapping.get(page_id, page_id)

    def _build_page_intro(self, page_id: str) -> str:
        mapping = {
            "map": "现在你进入的是地图页，这里可以查看景区内景点分布、当前位置以及推荐路线。如果你想去某个景点，可以直接对我说，带我去灵山梵宫，或者从南门到九龙灌浴怎么走。",
            "recommend": "现在你进入的是推荐页，这里会根据当前景区和你的游玩需求，为你推荐景点、玩法和路线。如果你是第一次来，可以直接问我，第一次来最值得看什么。",
            "route": "现在你进入的是路线页，这里可以查看推荐游览顺序和路线建议。如果你时间有限，也可以直接问我，半天怎么逛，或者适合亲子的游玩路线。",
            "scenic_detail": "现在你进入的是景点详情页，这里可以查看当前景点的介绍、亮点和相关讲解。如果你想听文化解说，可以直接问我，这个景点讲的是什么。",
            "home": "现在你在首页，这里可以快速进入地图、推荐和路线等页面。你也可以直接对我说你的需求，比如有什么景点，或者第一次来推荐看什么。",
            "current": "这是当前页面，如果你愿意，我可以继续给你介绍这个页面的用途。",
        }
        return mapping.get(page_id, "这个页面可以帮助你完成当前景区浏览、推荐和讲解相关操作。")

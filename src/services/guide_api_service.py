from __future__ import annotations

import json
import base64
import re
import traceback
from pathlib import Path
from typing import Any, Dict, List

from config import AppSettings
from api.schemas import (
    AskRequest,
    AskResponse,
    CommandRequest,
    GuideChatRequest,
    GuideChatResponse,
    GuideAnswerRequest,
    GuideAnswerResponse,
    MemoryClearResponse,
    NearbyRequest,
    NearbyResponse,
    PoiImportResponse,
    RetrievedContextItem,
    RoutePlanRequest,
    RoutePlanResponse,
    RouterResponse,
    TTSRequest,
    TTSResponse,
    UIEventRequest,
    VoiceCommandResponse,
)
from knowledge.service import RagKnowledgeService
from knowledge.scene_context import SceneContext
from llm import ChatMessage, build_llm_client
from modules.model_router import ModelRouter
from services.asr_service import XFYunASRService
from services.memory_service import ConversationMemoryService
from services.nearby_service import NearbyService
from services.poi_import_service import PoiImportService
from services.poi_repository import PoiRepository
from services.route_planner import build_route_plan
from services.tencent_map_client import TencentMapClient
from services.tts_service import XFYunTTSService


class GuideAPIService:
    """
    改造版：
    1. 保留现有 ask / guide_answer / command / ui_event / tts / voice_command 行为
    2. route_plan(RoutePlanRequest) 直接走新的腾讯地图路线规划
    3. 自动初始化 POIRepository，并优先使用本地 JSON 导入的 POI 数据
    """

    def __init__(
        self,
        settings: AppSettings,
        route_planner: Any | None = None,
        poi_repository: Any | None = None,
    ):
        self.settings = settings
        self.rag_service = RagKnowledgeService(settings)

        self.tencent_map_client = TencentMapClient(settings)

        self.poi_repository = poi_repository or self._build_default_poi_repository()
        self.poi_import_service = PoiImportService(self.poi_repository, self.tencent_map_client)
        self.nearby_service = NearbyService(self.poi_repository, self.tencent_map_client)
        self.memory_service = ConversationMemoryService(
            self.settings.project_root / "src" / "data" / "memory"
        )

        self.router = ModelRouter(
            llm_aggregator=None,
            vector_retriever=None,
            tencent_map_client=self.tencent_map_client,
            xunfei_tts=None,
            knowledge_service=self.rag_service,
            route_backend_client=None,
        )

        self.asr_service = XFYunASRService(settings)
        self.tts_service = XFYunTTSService()
        self.llm_client = build_llm_client(settings)

        self.route_planner = route_planner

    def _build_default_poi_repository(self) -> PoiRepository:
        poi_dir = self.settings.project_root / "src" / "data" / "poi"
        return PoiRepository(poi_dir)

    # =========================
    # 现有能力：保持不变
    # =========================

    def ask(self, req: AskRequest) -> AskResponse:
        scene_context = SceneContext(
            destination_id=req.destination_id,
            destination_name=req.destination_name,
            scenic_id=req.scenic_id,
            scenic_name=req.scenic_name,
            scope_mode=req.scope_mode,
        )

        result = self.rag_service.answer(
            question=req.query,
            scene_context=scene_context,
        )

        contexts: List[RetrievedContextItem] = [
            RetrievedContextItem(
                text=item.text,
                metadata=item.metadata,
                distance=item.distance,
                score=item.score,
            )
            for item in result.contexts
        ]

        return AskResponse(
            question=result.question,
            answer=result.answer,
            model=result.model,
            retrieved_contexts=contexts,
        )

    def guide_answer(self, req: GuideAnswerRequest) -> GuideAnswerResponse:
        ask_result = self.ask(
            AskRequest(
                query=req.query,
                destination_id=req.destination_id,
                destination_name=req.destination_name,
                scenic_id=req.scenic_id,
                scenic_name=req.scenic_name,
                scope_mode=req.scope_mode,
            )
        )

        references = self._extract_references(ask_result.answer)

        try:
            guide_text = self._rewrite_as_guide_answer(
                question=req.query,
                knowledge_answer=ask_result.answer,
                style=req.style,
                audience=req.audience,
                max_length=req.max_length,
                include_tips=req.include_tips,
                include_next_suggestion=req.include_next_suggestion,
                scenic_name=req.scenic_name or req.destination_name,
            )
        except Exception:
            guide_text = self._build_guide_answer_fallback(
                question=req.query,
                knowledge_answer=ask_result.answer,
                style=req.style,
                audience=req.audience,
                max_length=req.max_length,
                include_tips=req.include_tips,
                include_next_suggestion=req.include_next_suggestion,
                scenic_name=req.scenic_name or req.destination_name,
            )

        return GuideAnswerResponse(
            question=ask_result.question,
            knowledge_answer=ask_result.answer,
            guide_answer=guide_text,
            model=ask_result.model,
            references=references,
            retrieved_contexts=ask_result.retrieved_contexts,
            style=req.style,
            audience=req.audience,
            debug={
                "scope_mode": req.scope_mode,
                "destination_name": req.destination_name,
                "scenic_name": req.scenic_name,
                "include_tips": req.include_tips,
                "include_next_suggestion": req.include_next_suggestion,
            },
        )

    def command(self, req: CommandRequest) -> RouterResponse:
        scene_context = {
            "destination_id": req.destination_id,
            "destination_name": req.destination_name,
            "scenic_id": req.scenic_id,
            "scenic_name": req.scenic_name,
            "scope_mode": req.scope_mode,
        }
        result = self.router.handle(
            query=req.query,
            scene_context=scene_context,
            user_profile=req.user_profile,
        )
        return RouterResponse(**result)

    def ui_event(self, req: UIEventRequest) -> RouterResponse:
        scene_context = {
            "destination_id": req.destination_id,
            "destination_name": req.destination_name,
            "scenic_id": req.scenic_id,
            "scenic_name": req.scenic_name,
            "scope_mode": req.scope_mode,
        }
        result = self.router.handle_ui_event(
            event_type=req.event_type,
            page_id=req.page_id,
            scene_context=scene_context,
            user_profile=req.user_profile,
        )
        return RouterResponse(**result)

    def tts(self, req: TTSRequest) -> TTSResponse:
        try:
            text = (req.text or "").strip()
            if not text:
                raise ValueError("text 不能为空")

            if text[-1] in {"。", "！", "？", ".", "!", "?"}:
                synth_text = text + " "
            else:
                synth_text = text + "。 "

            audio_format = (req.audio_format or "mp3").strip().lower()

            audio_bytes = self.tts_service.synthesize_bytes(
                text=synth_text,
                voice=req.voice,
                speed=req.speed,
                volume=req.volume,
                pitch=req.pitch,
                audio_format=audio_format,
            )

            if isinstance(audio_bytes, bytearray):
                audio_bytes = bytes(audio_bytes)

            if not isinstance(audio_bytes, bytes):
                raise TypeError(
                    f"tts_service.synthesize_bytes must return bytes, got {type(audio_bytes)}"
                )

            if not audio_bytes:
                raise ValueError("TTS 返回为空音频")

            content_type = self.tts_service.get_content_type(audio_format)
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

            return TTSResponse(
                provider="xfyun",
                text=text,
                voice=req.voice,
                content_type=content_type,
                audio_base64=audio_base64,
            )

        except Exception as exc:
            print("TTS API ERROR:", exc)
            traceback.print_exc()
            raise

    def voice_command(
        self,
        audio_bytes: bytes,
        file_suffix: str,
        destination_id: str | None,
        destination_name: str | None,
        scenic_id: str | None,
        scenic_name: str | None,
        scope_mode: str,
        user_profile: dict,
        with_tts: bool,
        voice: str,
    ) -> VoiceCommandResponse:
        recognized_text = self.asr_service.transcribe_bytes(
            audio_bytes=audio_bytes,
            suffix=file_suffix,
        )

        command_result = self.command(
            CommandRequest(
                query=recognized_text,
                destination_id=destination_id,
                destination_name=destination_name,
                scenic_id=scenic_id,
                scenic_name=scenic_name,
                scope_mode=scope_mode,
                user_profile=user_profile or {},
            )
        )

        tts_result = None
        if with_tts and command_result.speech_text:
            tts_result = self.tts(
                TTSRequest(
                    text=command_result.speech_text,
                    voice=voice,
                    audio_format="mp3",
                )
            )

        return VoiceCommandResponse(
            recognized_text=recognized_text,
            intent=command_result.intent,
            action=command_result.action,
            speech_text=command_result.speech_text,
            ui_command=command_result.ui_command,
            data=command_result.data,
            tts=tts_result,
        )

    # =========================
    # 新路线能力：真正走腾讯地图 + POIRepository
    # =========================

    def route_plan(self, req: RoutePlanRequest) -> RoutePlanResponse:
        result = build_route_plan(
            req=req,
            tencent_map_client=self.tencent_map_client,
            poi_repository=self.poi_repository,
        )

        try:
            better_guide_answer = self._rewrite_route_guide_answer(
                req=req,
                route_resp=result,
            )
            result.data.guide_answer = better_guide_answer
            if result.ui_command is not None:
                result.ui_command["speech_text"] = better_guide_answer
        except Exception as exc:
            print(">>> rewrite route guide answer failed:", exc)
            traceback.print_exc()

        # 新增：直接调用 /api/v1/guide/route-plan 时，也写入会话记忆
        # 否则下一轮 /api/v1/guide/chat 问“那要走多久？”时，读不到 last_route。
        try:
            if getattr(req, "session_id", None):
                answer = (
                        result.data.guide_answer
                        or result.data.narration
                        or result.message
                        or ""
                )

                self.memory_service.update_from_turn(
                    session_id=req.session_id,
                    query=req.query or "",
                    response={
                        "intent": "route_plan",
                        "action": result.action,
                        "answer": answer,
                        "speech_text": answer,
                        "data": result.data.model_dump(),
                    },
                    user_profile=None,
                )
        except Exception as exc:
            print(">>> save route memory failed:", exc)
            traceback.print_exc()

        return result

    async def import_poi_file(
        self,
        file: Any,
        scenic_id: str,
        scenic_name: str | None = None,
        overwrite: bool = True,
        use_tencent_geocode: bool = True,
        city: str | None = None,
        address_hint: str | None = None,
    ) -> PoiImportResponse:
        result = await self.poi_import_service.import_poi_file(
            file=file,
            scenic_id=scenic_id,
            scenic_name=scenic_name,
            overwrite=overwrite,
            use_tencent_geocode=use_tencent_geocode,
            city=city,
            address_hint=address_hint,
        )
        return PoiImportResponse(**result)

    def search_nearby(self, req: NearbyRequest) -> NearbyResponse:
        if req.current_location is not None:
            center = {
                "name": "当前位置",
                "lat": req.current_location.lat,
                "lng": req.current_location.lng,
            }
        else:
            poi = self.poi_repository.find_poi(req.scenic_id, req.center_poi)
            if not poi:
                raise ValueError("无法识别 center_poi，请传可匹配的 POI 名称、别名或 poi_id")
            center = {
                "name": poi["name"],
                "lat": float(poi["lat"]),
                "lng": float(poi["lng"]),
            }

        return self.nearby_service.search_nearby(
            scenic_id=req.scenic_id,
            center=center,
            categories=req.categories,
            radius_m=req.radius_m,
            limit=req.limit,
        )

    def clear_memory(self, session_id: str) -> None:
        self.memory_service.clear_memory(session_id)

    def chat(self, req: GuideChatRequest) -> GuideChatResponse:
        memory_context = self.memory_service.build_context(req.session_id) if req.with_memory else {}
        memory_profile = dict(memory_context.get("profile") or {})
        merged_profile = self._merge_profiles(memory_profile, req.user_profile or {})
        rewritten_query = self._rewrite_query_with_memory(req.query, memory_context)

        if self._is_preference_update_query(req.query):
            updated_profile = self._apply_preference_update(merged_profile, req.query)
            response_dict = {
                "session_id": req.session_id,
                "intent": "preference_update",
                "action": "update_profile",
                "answer": "好的，我会记住你的偏好，后续尽量推荐更适合你的讲解和路线。",
                "speech_text": "好的，我会记住你的偏好，后续尽量推荐更适合你的讲解和路线。",
                "ui_command": {"type": "none"},
                "data": {"profile": updated_profile},
                "debug": {"rewritten_query": rewritten_query, "intent_source": "preference_rule"},
            }
            memory = self.memory_service.update_from_turn(
                session_id=req.session_id,
                query=req.query,
                response=response_dict,
                user_profile=updated_profile,
            )
            response_dict["memory"] = {
                "updated": True,
                "summary": memory.summary,
                "profile": memory.profile,
            }
            return GuideChatResponse(**response_dict)

        intent_guess = self._detect_chat_intent(rewritten_query, memory_context)
        if intent_guess == "route_context_followup":
            response_dict = self._handle_route_context_followup(
                req=req,
                memory_context=memory_context,
                rewritten_query=rewritten_query,
            )
        elif intent_guess == "route_followup":
            response_dict = self._handle_route_followup(req=req, memory_context=memory_context)
        elif intent_guess == "nearby_search":
            response_dict = self._handle_nearby_chat(req=req, memory_context=memory_context, rewritten_query=rewritten_query)
        elif intent_guess == "recommend":
            response_dict = self._handle_recommendation_chat(req=req, query=rewritten_query, merged_profile=merged_profile)
        else:
            router_response = self.command(
                CommandRequest(
                    query=rewritten_query,
                    destination_id=req.destination_id,
                    destination_name=req.destination_name,
                    scenic_id=req.scenic_id,
                    scenic_name=req.scenic_name,
                    scope_mode=req.scope_mode,
                    user_profile=merged_profile,
                )
            )
            response_dict = self._dispatch_chat_by_router_result(
                req=req,
                rewritten_query=rewritten_query,
                merged_profile=merged_profile,
                router_response=router_response,
                memory_context=memory_context,
            )

        if req.with_memory:
            memory = self.memory_service.update_from_turn(
                session_id=req.session_id,
                query=req.query,
                response=response_dict,
                user_profile=merged_profile,
            )
            response_dict["memory"] = {
                "updated": True,
                "summary": memory.summary,
                "profile": memory.profile,
                "last_poi": memory.last_poi,
                "last_route": memory.last_route,
            }
        else:
            response_dict["memory"] = {"updated": False}

        return GuideChatResponse(**response_dict)

    def _dispatch_chat_by_router_result(
        self,
        req: GuideChatRequest,
        rewritten_query: str,
        merged_profile: Dict[str, Any],
        router_response: RouterResponse,
        memory_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        debug = {
            "intent_source": "model_router",
            "rewritten_query": rewritten_query,
            "used_route_plan": False,
            "used_knowledge": False,
        }

        if router_response.intent == "route_plan":
            route_req = self._build_route_plan_request(
                req=req,
                rewritten_query=rewritten_query,
                router_response=router_response,
                merged_profile=merged_profile,
                memory_context=memory_context,
            )
            route_response = self.route_plan(route_req)
            debug["used_route_plan"] = True
            return {
                "session_id": req.session_id,
                "intent": "route_plan",
                "action": route_response.action,
                "answer": route_response.data.guide_answer or route_response.data.narration or route_response.message,
                "speech_text": (route_response.ui_command or {}).get("speech_text")
                or route_response.data.guide_answer
                or route_response.data.narration
                or route_response.message,
                "ui_command": route_response.ui_command or {"type": "none"},
                "data": route_response.data.model_dump(),
                "debug": debug,
            }

        if router_response.intent in {"ui_navigate_page", "ui_show_avatar", "ui_hide_avatar", "ui_close_page", "ui_page_intro"}:
            return {
                "session_id": req.session_id,
                "intent": router_response.intent,
                "action": router_response.action,
                "answer": router_response.speech_text,
                "speech_text": router_response.speech_text,
                "ui_command": router_response.ui_command or {"type": "none"},
                "data": router_response.data or {},
                "debug": debug,
            }

        guide_result = self.guide_answer(
            GuideAnswerRequest(
                query=rewritten_query,
                destination_id=req.destination_id,
                destination_name=req.destination_name,
                scenic_id=req.scenic_id,
                scenic_name=req.scenic_name,
                scope_mode=req.scope_mode,
                style="guide",
                audience=self._resolve_audience(merged_profile),
                max_length=500,
                include_tips=True,
                include_next_suggestion=True,
            )
        )
        debug["used_knowledge"] = True
        return {
            "session_id": req.session_id,
            "intent": router_response.intent if router_response.intent != "unknown" else "knowledge_qa",
            "action": "guide_answer",
            "answer": guide_result.guide_answer,
            "speech_text": guide_result.guide_answer,
            "ui_command": {"type": "none"},
            "data": {
                "references": guide_result.references,
                "retrieved_contexts": [item.model_dump() for item in guide_result.retrieved_contexts],
                "spot_name": self._guess_last_poi_from_query(rewritten_query, req.scenic_name),
            },
            "debug": debug,
        }

    def _handle_recommendation_chat(
        self,
        req: GuideChatRequest,
        query: str,
        merged_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        prompt = self._build_recommendation_prompt(query=query, profile=merged_profile)
        guide_result = self.guide_answer(
            GuideAnswerRequest(
                query=prompt,
                destination_id=req.destination_id,
                destination_name=req.destination_name,
                scenic_id=req.scenic_id,
                scenic_name=req.scenic_name,
                scope_mode=req.scope_mode,
                style="guide",
                audience=self._resolve_audience(merged_profile),
                max_length=520,
                include_tips=True,
                include_next_suggestion=True,
            )
        )
        return {
            "session_id": req.session_id,
            "intent": "itinerary_recommend",
            "action": "show_recommendation",
            "answer": guide_result.guide_answer,
            "speech_text": guide_result.guide_answer,
            "ui_command": {"type": "show_recommendation"},
            "data": {"recommended_pois": [], "references": guide_result.references},
            "debug": {"intent_source": "recommend_rule", "used_knowledge": True, "used_route_plan": False, "rewritten_query": query},
        }

    def _handle_nearby_chat(
        self,
        req: GuideChatRequest,
        memory_context: Dict[str, Any],
        rewritten_query: str,
    ) -> Dict[str, Any]:
        categories = self._infer_nearby_categories(rewritten_query)
        current_location = req.current_location
        center_poi = None
        if current_location is None:
            center_poi = memory_context.get("last_poi")
            if not center_poi:
                return {
                    "session_id": req.session_id,
                    "intent": "nearby_search",
                    "action": "clarify_location",
                    "answer": "我可以帮你查附近设施，请告诉我你当前的位置，或者先说一个中心点位。",
                    "speech_text": "我可以帮你查附近设施，请告诉我你当前的位置，或者先说一个中心点位。",
                    "ui_command": {"type": "none"},
                    "data": {},
                    "debug": {"intent_source": "nearby_rule", "rewritten_query": rewritten_query},
                }

        nearby_response = self.search_nearby(
            NearbyRequest(
                scenic_id=req.scenic_id or "",
                center_poi=center_poi,
                current_location=current_location,
                categories=categories,
                radius_m=500,
                limit=10,
            )
        )
        return {
            "session_id": req.session_id,
            "intent": "nearby_search",
            "action": "show_nearby",
            "answer": nearby_response.message,
            "speech_text": nearby_response.message,
            "ui_command": nearby_response.ui_command,
            "data": {"center": nearby_response.center, "results": nearby_response.results, "radius_m": nearby_response.radius_m},
            "debug": {"intent_source": "nearby_rule", "rewritten_query": rewritten_query},
        }


    def _handle_route_context_followup(
        self,
        req: GuideChatRequest,
        memory_context: Dict[str, Any],
        rewritten_query: str,
    ) -> Dict[str, Any]:
        """
        处理路线相关追问：
        1. “路上有什么好玩的 / 沿途有什么 / 途中经过什么”
        2. “适合带老人/小孩/亲子/拍照/溜达吗 / 累不累 / 好走吗”

        必须返回完整 response_dict，不能只返回字符串。
        """
        if not isinstance(memory_context, dict):
            memory_context = {}

        last_route = memory_context.get("last_route") or {}
        if isinstance(last_route, str):
            try:
                parsed_route = json.loads(last_route)
                last_route = parsed_route if isinstance(parsed_route, dict) else {}
            except Exception:
                last_route = {}

        if not isinstance(last_route, dict):
            last_route = {}

        if self._is_route_suitability_query(rewritten_query):
            answer = self._build_route_suitability_answer(
                query=rewritten_query,
                memory_context={"last_route": last_route},
            )
            summary = last_route.get("summary") if isinstance(last_route.get("summary"), dict) else {}
            return {
                "session_id": req.session_id,
                "intent": "route_context_followup",
                "action": "route_suitability",
                "answer": answer,
                "speech_text": answer,
                "ui_command": {
                    "type": "show_route_context",
                    "last_route": last_route,
                    "along_pois": [],
                },
                "data": {
                    "last_route": last_route,
                    "along_pois": [],
                    "summary": summary or {},
                },
                "debug": {
                    "intent_source": "route_suitability_rule",
                    "memory_found": bool(last_route),
                    "rewritten_query": rewritten_query,
                },
            }

        if not last_route:
            return {
                "session_id": req.session_id,
                "intent": "route_context_followup",
                "action": "clarify_route",
                "answer": "我还没有找到上一条路线记录。你可以先问我一条路线，比如“从灵山大佛到九龙灌浴怎么走”，然后我再告诉你路上有什么可以顺便看。",
                "speech_text": "我还没有找到上一条路线记录。你可以先问我一条路线，比如从灵山大佛到九龙灌浴怎么走。",
                "ui_command": {"type": "none"},
                "data": {"last_route": {}},
                "debug": {
                    "intent_source": "route_context_followup_rule",
                    "memory_found": False,
                    "rewritten_query": rewritten_query,
                },
            }

        start_poi = last_route.get("start_poi")
        end_poi = last_route.get("end_poi")
        summary = last_route.get("summary") or {}
        if isinstance(summary, str):
            try:
                parsed_summary = json.loads(summary)
                summary = parsed_summary if isinstance(parsed_summary, dict) else {}
            except Exception:
                summary = {}
        if not isinstance(summary, dict):
            summary = {}

        distance = summary.get("total_distance_m")
        duration = summary.get("total_duration_min")

        scenic_id = req.scenic_id or ""
        along_pois = self._find_pois_along_last_route(
            scenic_id=scenic_id,
            start_poi=start_poi,
            end_poi=end_poi,
            limit=5,
        )

        if along_pois:
            names = "、".join(item.get("name", "") for item in along_pois if item.get("name"))
            intro_parts = []
            for item in along_pois[:3]:
                name = item.get("name", "")
                intro = (item.get("intro") or item.get("address") or "").strip()
                if intro:
                    intro_parts.append(f"{name}可以顺路留意，{self._compress_text(intro, 45)}")
                elif name:
                    intro_parts.append(f"{name}可以顺路看一眼")

            route_text = f"从{start_poi}到{end_poi}这段路上，" if start_poi and end_poi else ""
            answer = f"{route_text}可以顺路看看{names}。"
            if intro_parts:
                answer += "其中，" + "；".join(intro_parts) + "。"
            if duration is not None or distance is not None:
                extra = []
                if distance is not None:
                    extra.append(f"全程约{distance}米")
                if duration is not None:
                    extra.append(f"步行约{duration}分钟")
                answer += "这段路" + "，".join(extra) + "，建议边走边看，不用专门绕太远。"
        else:
            route_text = f"从{start_poi}到{end_poi}这段路" if start_poi and end_poi else "这段路"
            time_text = ""
            if distance is not None and duration is not None:
                time_text = f"全程约{distance}米，步行大约{duration}分钟，"

            answer = (
                f"{route_text}{time_text}主要建议把重点放在终点{end_poi or '目的地'}。"
                f"路上可以留意沿途景观和导览标识，适合边走边拍照；到达后再重点欣赏{end_poi or '目的地'}的核心看点。"
            )

        return {
            "session_id": req.session_id,
            "intent": "route_context_followup",
            "action": "route_along_pois",
            "answer": answer,
            "speech_text": answer,
            "ui_command": {
                "type": "show_route_context",
                "last_route": last_route,
                "along_pois": along_pois,
            },
            "data": {
                "last_route": last_route,
                "along_pois": along_pois,
                "summary": summary,
            },
            "debug": {
                "intent_source": "route_context_followup_rule",
                "memory_found": True,
                "poi_source": "local_poi_repository",
                "rewritten_query": rewritten_query,
            },
        }

    def _find_pois_along_last_route(
        self,
        scenic_id: str,
        start_poi: str | None,
        end_poi: str | None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        从本地 POI 中粗略找“起终点连线附近”的点位。
        不调用外部 LLM，也不调用腾讯接口；只是做一个稳定兜底。
        """
        if not scenic_id or not start_poi or not end_poi:
            return []

        start = self.poi_repository.find_poi(scenic_id, start_poi)
        end = self.poi_repository.find_poi(scenic_id, end_poi)
        if not start or not end:
            return []

        try:
            start_lat = float(start["lat"])
            start_lng = float(start["lng"])
            end_lat = float(end["lat"])
            end_lng = float(end["lng"])
        except (KeyError, TypeError, ValueError):
            return []

        candidates = []
        for poi in self.poi_repository.filter_valid_route_pois(scenic_id):
            name = str(poi.get("name") or "")
            if not name or name in {start_poi, end_poi}:
                continue

            try:
                lat = float(poi["lat"])
                lng = float(poi["lng"])
            except (KeyError, TypeError, ValueError):
                continue

            score = self._point_to_segment_score(
                lat=lat,
                lng=lng,
                start_lat=start_lat,
                start_lng=start_lng,
                end_lat=end_lat,
                end_lng=end_lng,
            )

            # 350 米以内认为“路上/沿途附近”比较合理。
            if score["distance_to_segment_m"] <= 350:
                copied = dict(poi)
                copied["distance_to_route_m"] = int(score["distance_to_segment_m"])
                copied["_route_progress"] = score["progress"]
                candidates.append(copied)

        candidates.sort(
            key=lambda item: (
                float(item.get("_route_progress", 0)),
                int(item.get("distance_to_route_m", 999999)),
            )
        )

        result = []
        for item in candidates[:limit]:
            result.append(
                {
                    "poi_id": item.get("poi_id"),
                    "name": item.get("name"),
                    "point_type": item.get("point_type"),
                    "intro": item.get("intro", ""),
                    "address": item.get("address", ""),
                    "tags": item.get("tags", []),
                    "distance_to_route_m": item.get("distance_to_route_m"),
                }
            )
        return result

    @staticmethod
    def _point_to_segment_score(
        lat: float,
        lng: float,
        start_lat: float,
        start_lng: float,
        end_lat: float,
        end_lng: float,
    ) -> Dict[str, float]:
        """
        用近似平面坐标计算点到起终点线段的距离，单位米。
        对景区内部短距离足够稳定。
        """
        mean_lat = (start_lat + end_lat) / 2.0
        meter_per_lat = 111320.0
        meter_per_lng = 111320.0 * max(0.1, __import__("math").cos(__import__("math").radians(mean_lat)))

        sx, sy = start_lng * meter_per_lng, start_lat * meter_per_lat
        ex, ey = end_lng * meter_per_lng, end_lat * meter_per_lat
        px, py = lng * meter_per_lng, lat * meter_per_lat

        vx, vy = ex - sx, ey - sy
        wx, wy = px - sx, py - sy

        length_sq = vx * vx + vy * vy
        if length_sq <= 0:
            dx, dy = px - sx, py - sy
            return {"distance_to_segment_m": (dx * dx + dy * dy) ** 0.5, "progress": 0.0}

        t = (wx * vx + wy * vy) / length_sq
        t_clamped = max(0.0, min(1.0, t))

        proj_x = sx + t_clamped * vx
        proj_y = sy + t_clamped * vy
        dx, dy = px - proj_x, py - proj_y

        return {
            "distance_to_segment_m": (dx * dx + dy * dy) ** 0.5,
            "progress": t_clamped,
        }

    def _handle_route_followup(
            self,
            req: GuideChatRequest,
            memory_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        last_route = memory_context.get("last_route") or {}

        if not last_route:
            return {
                "session_id": req.session_id,
                "intent": "route_plan",
                "action": "clarify_route",
                "answer": "你是想继续问刚才那条路线吗？我这边还没有找到上一条路线记录。你可以再告诉我起点和终点，比如“从灵山大佛到九龙灌浴怎么走”。",
                "speech_text": "你是想继续问刚才那条路线吗？我这边还没有找到上一条路线记录。你可以再告诉我起点和终点。",
                "ui_command": {"type": "none"},
                "data": {
                    "last_route": {},
                },
                "debug": {
                    "intent_source": "route_followup_rule",
                    "memory_found": False,
                },
            }

        summary = last_route.get("summary") or {}
        duration = summary.get("total_duration_min")
        distance = summary.get("total_distance_m")
        start_poi = last_route.get("start_poi")
        end_poi = last_route.get("end_poi")
        mode = last_route.get("mode") or summary.get("mode") or "walk"

        if duration is None and distance is None:
            return {
                "session_id": req.session_id,
                "intent": "route_plan",
                "action": "clarify_route",
                "answer": "我找到了上一条路线记录，但里面没有完整的距离和时间信息。你可以重新说一下起点和终点，我再帮你规划一次。",
                "speech_text": "我找到了上一条路线记录，但里面没有完整的距离和时间信息。你可以重新说一下起点和终点，我再帮你规划一次。",
                "ui_command": {"type": "none"},
                "data": {
                    "last_route": last_route,
                },
                "debug": {
                    "intent_source": "route_followup_rule",
                    "memory_found": True,
                    "summary_found": False,
                },
            }

        parts = []

        if start_poi and end_poi:
            parts.append(f"从{start_poi}到{end_poi}")

        if duration is not None:
            parts.append(f"预计步行大约 {duration} 分钟")

        if distance is not None:
            parts.append(f"全程约 {distance} 米")

        answer = "，".join(parts) + "。"

        if mode == "walk":
            answer += " 如果你走得慢一点，可以多预留几分钟。"

        return {
            "session_id": req.session_id,
            "intent": "route_plan",
            "action": "route_summary",
            "answer": answer,
            "speech_text": answer,
            "ui_command": {
                "type": "show_route_summary",
                "last_route": last_route,
            },
            "data": {
                "summary": summary,
                "last_route": last_route,
            },
            "debug": {
                "intent_source": "route_followup_rule",
                "memory_found": True,
                "summary_found": True,
            },
        }


    def _rewrite_query_with_memory(
        self,
        query: str,
        memory_context: Dict[str, Any] | None = None,
    ) -> str:
        """
        根据会话记忆改写用户追问。

        1. 路线追问，比如“那要走多久 / 多远 / 还远吗”，不在这里改写，
           直接交给 _detect_chat_intent -> _handle_route_followup。
        2. 知识追问，比如“它有什么典故 / 这里有什么特点”，如果有 last_poi，
           改写成“灵山大佛有什么典故”这类完整问题。
        """
        query = (query or "").strip()
        memory_context = memory_context or {}

        if not query:
            return query

        route_context_keywords = [
            "路上有什么",
            "路上有啥",
            "路上好玩",
            "路上有什么好玩",
            "沿途有什么",
            "沿途有啥",
            "沿途好玩",
            "途中有什么",
            "途中有啥",
            "会经过什么",
            "经过哪些",
            "顺路看什么",
            "顺路有什么",
        ]

        route_follow_keywords = [
            "多久",
            "多长时间",
            "要走多久",
            "走多久",
            "几分钟",
            "多少分钟",
            "多远",
            "距离",
            "还远吗",
            "远不远",
            "走多远",
            "要走多远",
            "上一条路线",
            "刚才那条路线",
            "刚刚那条路线",
        ]

        if any(keyword in query for keyword in route_follow_keywords):
            return query

        last_poi = memory_context.get("last_poi")
        if not last_poi:
            return query

        pronoun_prefixes = [
            "它",
            "这个",
            "这里",
            "那里",
            "该景点",
            "这个景点",
            "这个地方",
        ]

        for prefix in pronoun_prefixes:
            if query.startswith(prefix):
                return f"{last_poi}{query[len(prefix):]}"

        return query


    def _parse_route_pois_from_query(self, query: str) -> Dict[str, Any]:
        """
        从中文路线问句里兜底提取起点、终点和出行方式。

        支持：
        - 从A到B怎么走
        - A到B怎么走
        - 去B怎么走
        - 到B怎么走
        - 从A去B
        """
        query = (query or "").strip()
        result: Dict[str, Any] = {
            "start_poi": None,
            "end_poi": None,
            "mode": "walk",
        }

        if not query:
            return result

        if any(word in query for word in ["骑车", "骑行", "自行车"]):
            result["mode"] = "bike"
        elif any(word in query for word in ["开车", "驾车", "自驾"]):
            result["mode"] = "drive"
        else:
            result["mode"] = "walk"

        cleaned = query
        cleaned = cleaned.replace("？", "?")
        cleaned = re.sub(r"[，。！？?]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # 从 A 到 B 怎么走 / 从 A 去 B
        patterns = [
            r"从\s*(?P<start>.+?)\s*(?:到|去|前往)\s*(?P<end>.+?)(?:怎么走|如何走|路线|导航|要多久|多久|多远|$)",
            r"(?P<start>.+?)\s*(?:到|去|前往)\s*(?P<end>.+?)(?:怎么走|如何走|路线|导航|要多久|多久|多远|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, cleaned)
            if not match:
                continue

            start = self._clean_route_poi_name(match.group("start"))
            end = self._clean_route_poi_name(match.group("end"))

            if start and end and start != end:
                result["start_poi"] = start
                result["end_poi"] = end
                return result

        # 去 B 怎么走 / 到 B 怎么走
        match = re.search(r"(?:去|到|前往)\s*(?P<end>.+?)(?:怎么走|如何走|路线|导航|要多久|多久|多远|$)", cleaned)
        if match:
            end = self._clean_route_poi_name(match.group("end"))
            if end:
                result["end_poi"] = end

        return result

    @staticmethod
    def _clean_route_poi_name(value: str | None) -> str | None:
        text = (value or "").strip()
        if not text:
            return None

        remove_words = [
            "请问",
            "我想",
            "我要",
            "帮我",
            "给我",
            "一下",
            "怎么走",
            "如何走",
            "路线",
            "导航",
            "要多久",
            "多久",
            "多远",
            "步行",
            "走路",
            "骑车",
            "骑行",
            "开车",
            "驾车",
        ]

        for word in remove_words:
            text = text.replace(word, "")

        text = text.strip(" ，。！？?、:：；;")
        text = re.sub(r"\s+", "", text)

        return text or None


    def _build_route_plan_request(
        self,
        req: GuideChatRequest,
        rewritten_query: str,
        router_response: RouterResponse,
        merged_profile: Dict[str, Any],
        memory_context: Dict[str, Any],
    ) -> RoutePlanRequest:
        data = router_response.data or {}
        ui_command = router_response.ui_command or {}
        scenic_id = data.get("scenic_id") or ui_command.get("scenic_id") or req.scenic_id

        if not scenic_id:
            raise ValueError("路线问题缺少 scenic_id")

        # 1. 优先使用 router 明确抽取出来的字段
        start_poi = (
            data.get("start_poi")
            or data.get("start")
            or data.get("origin")
            or ui_command.get("start_poi")
            or ui_command.get("start")
            or ui_command.get("origin")
        )
        end_poi = (
            data.get("end_poi")
            or data.get("end")
            or data.get("destination")
            or ui_command.get("end_poi")
            or ui_command.get("end")
            or ui_command.get("destination")
        )
        mode = data.get("mode") or ui_command.get("mode") or "walk"

        # 2. 如果 router 没抽出来，就从中文问句兜底解析
        parsed_route = self._parse_route_pois_from_query(rewritten_query)

        if not start_poi:
            start_poi = parsed_route.get("start_poi")
        if not end_poi:
            end_poi = parsed_route.get("end_poi")
        if not mode:
            mode = parsed_route.get("mode") or "walk"

        # 3. 如果还是没有起点，可以用当前位置；没有当前位置时才尝试上一次路线终点/起点
        last_route = memory_context.get("last_route") or {}

        if not start_poi and req.current_location is None:
            start_poi = (
                last_route.get("end_poi")
                or last_route.get("start_poi")
            )

        # 4. 如果是上下文追问，才允许从 last_route 继承终点；
        #    普通新路线问题不要强行继承旧终点，避免走错。
        if not end_poi and self._is_route_followup_query(rewritten_query):
            end_poi = last_route.get("end_poi")

        if isinstance(start_poi, dict):
            start_poi = start_poi.get("name") or start_poi.get("poi_name") or start_poi.get("id")
        if isinstance(end_poi, dict):
            end_poi = end_poi.get("name") or end_poi.get("poi_name") or end_poi.get("id")

        start_poi = str(start_poi).strip() if start_poi else None
        end_poi = str(end_poi).strip() if end_poi else None

        if not end_poi:
            raise ValueError(
                f"无法识别终点 end_poi，请传景点名称或已知 poi_id。"
                f"当前问题：{rewritten_query}"
            )

        return RoutePlanRequest(
            session_id=req.session_id,
            scenic_id=scenic_id,
            query=rewritten_query,
            mode=mode or "walk",
            start_poi=start_poi,
            end_poi=end_poi,
            current_location=req.current_location,
            waypoints=[],
            interests=list(merged_profile.get("interests") or []),
            max_walk_minutes=None,
            avoid_stairs=bool(merged_profile.get("avoid_stairs") or merged_profile.get("mobility_limited")),
            family_friendly=bool(merged_profile.get("family_friendly") or merged_profile.get("travel_type") == "family"),
        )

    @staticmethod
    def _is_route_followup_query(query: str) -> bool:
        query = (query or "").strip()
        follow_keywords = [
            "多久",
            "多长时间",
            "几分钟",
            "多少分钟",
            "多远",
            "还远吗",
            "远不远",
            "上一条路线",
            "刚才那条路线",
            "刚刚那条路线",
            "那条路线",
            "这条路线",
        ]
        return any(keyword in query for keyword in follow_keywords)


    def _is_route_suitability_query(self, query: str | None = None) -> bool:
        """
        判断是否是基于上一条路线的适配性追问。

        覆盖自然说法：
        - 适合带老人拍照留念吗
        - 适合带小孩吗 / 带孩子方便吗 / 亲子能走吗
        - 这条路累不累 / 好不好走 / 方便溜达吗
        - 能不能推轮椅 / 无障碍方便吗
        - 这段路适合拍照吗 / 能打卡吗
        """
        query = (query or "").strip()
        if not query:
            return False

        people_words = [
            "老人", "长辈", "父母", "叔叔阿姨",
            "孩子", "小孩", "小朋友", "宝宝", "儿童", "亲子",
            "轮椅", "推车", "婴儿车",
        ]

        scene_words = [
            "拍照", "留念", "合影", "打卡", "拍", "照相",
            "溜达", "逛逛", "慢慢走", "边走边看",
        ]

        suitability_words = [
            "适合", "方不方便", "方便吗", "方便不", "方便",
            "能走", "好走", "好不好走", "累不累", "会不会累",
            "远不远", "吃力", "费劲", "安全", "安全吗",
            "可以吗", "可不可以", "能不能", "行不行",
            "无障碍", "推轮椅", "推车",
        ]

        route_reference_words = [
            "这条路", "这段路", "这条路线", "这段路线",
            "刚才那条", "刚刚那条", "上一条路线", "路上", "沿途", "途中",
        ]

        # 明确路线指代 + 适配性词
        if any(word in query for word in route_reference_words) and any(word in query for word in suitability_words + scene_words + people_words):
            return True

        # 人群 + 适配性
        if any(word in query for word in people_words) and any(word in query for word in suitability_words + scene_words):
            return True

        # 拍照/打卡/溜达 + 适配性
        if any(word in query for word in scene_words) and any(word in query for word in suitability_words):
            return True

        # 简短追问，例如“累不累？”“好走吗？”在有 last_route 时由上层判断后进入这里
        short_followups = [
            "累不累", "会不会累", "好走吗", "好不好走", "远不远",
            "方便吗", "安全吗", "适合吗", "能拍照吗", "好拍照吗",
        ]
        if any(word in query for word in short_followups):
            return True

        return False

    def _build_route_suitability_answer(
        self,
        query: str,
        memory_context: Dict[str, Any] | None = None,
    ) -> str:
        """
        根据上一条路线记忆回答“适合老人/孩子/拍照/累不累/好走吗”等问题。
        不调用外部 LLM，避免外部接口异常导致 500。
        """
        query = (query or "").strip()

        if not isinstance(memory_context, dict):
            memory_context = {}

        last_route = memory_context.get("last_route") or {}
        if isinstance(last_route, str):
            try:
                parsed_route = json.loads(last_route)
                last_route = parsed_route if isinstance(parsed_route, dict) else {}
            except Exception:
                last_route = {}

        if not isinstance(last_route, dict):
            last_route = {}

        start_poi = last_route.get("start_poi") or last_route.get("start") or "起点"
        end_poi = last_route.get("end_poi") or last_route.get("end") or "终点"
        mode = last_route.get("mode") or "walk"

        summary = last_route.get("summary") or {}
        if isinstance(summary, str):
            try:
                parsed_summary = json.loads(summary)
                summary = parsed_summary if isinstance(parsed_summary, dict) else {}
            except Exception:
                summary = {}

        if not isinstance(summary, dict):
            summary = {}

        distance_m = summary.get("total_distance_m")
        duration_min = summary.get("total_duration_min")
        mode = summary.get("mode") or mode

        mode_text = {"walk": "步行", "drive": "驾车", "bike": "骑行"}.get(str(mode).lower(), "步行")

        try:
            distance_value = int(float(distance_m)) if distance_m is not None else None
            distance_text = f"全程约 {distance_value} 米" if distance_value is not None else "距离不算太长"
        except Exception:
            distance_value = None
            distance_text = "距离不算太长"

        try:
            duration_value = int(float(duration_min)) if duration_min is not None else None
            duration_text = f"正常{mode_text}约 {duration_value} 分钟" if duration_value is not None else f"{mode_text}时间建议按实际体力预留"
        except Exception:
            duration_value = None
            duration_text = f"{mode_text}时间建议按实际体力预留"

        elderly = any(keyword in query for keyword in ["老人", "长辈", "叔叔阿姨", "父母"])
        child = any(keyword in query for keyword in ["孩子", "小孩", "小朋友", "宝宝", "儿童", "亲子"])
        photo = any(keyword in query for keyword in ["拍照", "留念", "打卡", "合影", "照相", "拍"])
        stroll = any(keyword in query for keyword in ["溜达", "逛逛", "慢慢走", "边走边看"])
        wheelchair = any(keyword in query for keyword in ["轮椅", "推车", "婴儿车", "无障碍"])
        tired = any(keyword in query for keyword in ["累不累", "会不会累", "好走", "方便", "远不远", "吃力", "费劲"])

        has_route = bool(last_route)
        if has_route:
            route_prefix = f"刚才这条路线是从{start_poi}到{end_poi}，{distance_text}，{duration_text}。"
        else:
            route_prefix = "如果是接着刚才那条路线来说，建议以现场路况和同行人体力为准。"

        parts: List[str] = []

        if elderly:
            parts.append(
                f"适合带老人，但建议放慢节奏。{route_prefix}"
                "老人同行时不要赶路，可以边走边停，优先选路面平稳、开阔的位置休息和拍照。"
            )
        elif child:
            parts.append(
                f"适合带小朋友，但建议控制节奏。{route_prefix}"
                "孩子同行时可以边走边讲、边看边停，不要连续赶路；如果人多，尽量牵好孩子，避开拥挤点位。"
            )
        elif wheelchair:
            parts.append(
                f"如果要推轮椅或婴儿车，要更谨慎一点。{route_prefix}"
                "建议现场优先选择平整主路，遇到台阶、坡道或人流密集区域时不要强行通过，可以向景区工作人员确认无障碍路线。"
            )
        elif photo:
            parts.append(
                f"适合拍照留念。{route_prefix}"
                "建议选择视野开阔、人流不太拥挤的位置拍照，不要在通道中间停留太久。"
            )
        elif tired or stroll:
            parts.append(
                f"这条路线适合慢慢走。{route_prefix}"
                "如果同行人走得慢，可以多预留几分钟，中途看到合适位置就停下来休息一下。"
            )
        else:
            parts.append(
                f"可以参考刚才这条路线。{route_prefix}"
                "整体建议根据同行人的体力放慢节奏，不用赶路。"
            )

        if photo and has_route:
            parts.append(
                f"拍照上，可以重点抓住两个点：一是{start_poi}附近的标志性背景，"
                f"二是到达{end_poi}后再拍目的地景观。这样照片既有出发点，也有终点记忆。"
            )

        if child:
            parts.append("如果孩子年龄小，建议避开表演散场或人流集中的时间段，体验会更轻松。")

        if elderly:
            parts.append("如果老人腿脚一般，建议把这段按更轻松的 20 到 25 分钟来安排。")

        if has_route and end_poi and end_poi != "终点":
            parts.append(f"到{end_poi}后可以先找一个不挡路的位置休息一下，再继续看景或拍合影。")

        return "".join(parts)

    def _detect_chat_intent(
        self,
        query: str,
        memory_context: Dict[str, Any] | None = None,
    ) -> str:
        """
        统一导游 chat 的轻量意图识别。

        多轮规则：
        - 有 last_route 时，“适合老人/小孩/亲子/拍照/溜达/累不累/好走吗”都按路线追问处理
        - 明确“路上有什么/沿途有什么”按路线沿途追问
        - 明确“多久/多远/继续走”按路线时长距离追问
        - 只有明确“我喜欢/帮我记住/以后优先”才会走偏好更新
        """
        query = (query or "").strip()
        memory_context = memory_context if isinstance(memory_context, dict) else {}

        route_context_keywords = [
            "路上有什么", "路上有啥", "路上好玩", "路上好玩的", "路上好玩的吗",
            "路上有什么好玩", "路上有什么好玩的吗", "沿途有什么", "沿途有啥",
            "沿途好玩", "沿途景点", "沿途讲讲", "沿途介绍", "途中有什么",
            "途中有啥", "途中好玩", "路过什么", "会路过什么", "经过什么",
            "会经过什么", "顺路有什么", "顺路有啥", "顺路景点", "顺路看什么", "附近顺路",
        ]

        route_follow_keywords = [
            "多久", "多长时间", "要走多久", "走多久", "还要多久", "需要多久",
            "几分钟", "多少分钟", "要几分钟", "走几分钟", "多远", "距离",
            "还有多远", "还远吗", "远不远", "走多远", "要走多远",
            "怎么走", "往哪走", "继续走", "下一步", "下一段", "下一站",
            "然后呢", "接下来", "刚才那条路线", "刚刚那条路线", "上一条路线",
            "这条路线", "这段路",
        ]

        nearby_keywords = [
            "附近", "最近", "周边", "旁边", "厕所", "卫生间", "洗手间",
            "餐厅", "吃饭", "小吃", "美食", "游客中心", "服务中心",
            "停车场", "观光车", "乘车点",
        ]

        recommend_keywords = [
            "推荐", "怎么玩", "怎么逛", "路线推荐", "游玩路线",
            "半日游", "一日游", "亲子路线", "老人路线", "少走路路线", "轻松路线",
        ]

        route_plan_keywords = [
            "怎么去", "怎么到", "怎么走到", "带我去", "导航",
            "规划路线", "走到", "前往",
        ]

        has_last_route = bool(memory_context.get("last_route"))

        if any(keyword in query for keyword in route_context_keywords):
            return "route_context_followup"

        if has_last_route and self._is_route_suitability_query(query):
            return "route_context_followup"

        if any(keyword in query for keyword in route_follow_keywords):
            return "route_followup"

        if any(keyword in query for keyword in nearby_keywords):
            return "nearby_search"

        if any(keyword in query for keyword in recommend_keywords):
            return "itinerary_recommend"

        if any(keyword in query for keyword in route_plan_keywords):
            return "route_plan"

        if re.search(r"从.+到.+(怎么走|怎么去|路线|导航|走法)?", query):
            return "route_plan"
        if re.search(r".+到.+(怎么走|怎么去|路线|导航|走法)", query):
            return "route_plan"

        return "qa"

    def _is_preference_update_query(self, query: str | None = None) -> bool:
        """
        判断用户是否明确在更新个人偏好。
        不能因为出现“老人、亲子、拍照、美食”等词就直接判定为偏好更新。
        """
        query = (query or "").strip()
        if not query:
            return False

        question_markers = [
            "吗", "么", "嘛", "？", "?", "适合", "可以", "能不能", "能否",
            "是不是", "怎么样", "好不好", "推荐吗", "值得",
        ]
        explicit_memory_markers = [
            "帮我记住", "记住", "以后", "后面", "接下来", "我的偏好", "偏好是", "我偏好",
        ]

        if any(marker in query for marker in question_markers):
            if not any(marker in query for marker in explicit_memory_markers):
                return False

        explicit_update_patterns = [
            r"我喜欢.+", r"我比较喜欢.+", r"我更喜欢.+", r"我偏好.+",
            r"我的偏好是.+", r"我想看.+", r"我想去.+", r"我不喜欢.+",
            r"我不想.+", r"不想走太多", r"少走路", r"帮我记住.+",
            r"记住.+", r"以后.*推荐.+", r"以后.*优先.+", r"后面.*推荐.+",
            r"后面.*优先.+", r"接下来.*推荐.+", r"接下来.*优先.+",
        ]

        return any(re.search(pattern, query) for pattern in explicit_update_patterns)

    def _apply_preference_update(self, profile: Dict[str, Any], query: str) -> Dict[str, Any]:
        updated = dict(profile)
        interests = list(updated.get("interests") or [])
        if "我带孩子" in query:
            updated["travel_type"] = "family"
            updated["family_friendly"] = True
        if "不想走太远" in query or "我累了" in query:
            updated["pace"] = "slow"
            updated["avoid_long_walk"] = True
        if "喜欢拍照" in query:
            interests.append("photo")
        if "喜欢历史" in query or "历史文化" in query:
            interests.append("history")
        if "腿脚不太方便" in query:
            updated["mobility_limited"] = True
            updated["avoid_stairs"] = True
            updated["pace"] = "slow"
        if "半天时间" in query:
            updated["time_budget"] = "half_day"
        if "详细一点" in query:
            updated["answer_style"] = "detailed"
        if "简单说" in query:
            updated["answer_style"] = "concise"
        updated["interests"] = list(dict.fromkeys(interests))
        return updated

    @staticmethod
    def _merge_profiles(memory_profile: Dict[str, Any], user_profile: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(memory_profile or {})
        merged.update(user_profile or {})
        merged["interests"] = list(dict.fromkeys([*(memory_profile.get("interests") or []), *(user_profile.get("interests") or [])]))
        return merged

    @staticmethod
    def _resolve_audience(profile: Dict[str, Any]) -> str:
        if profile.get("travel_type") == "family" or profile.get("family_friendly"):
            return "parent_child"
        if "history" in (profile.get("interests") or []):
            return "history"
        return "general"

    @staticmethod
    def _infer_nearby_categories(query: str) -> List[str]:
        mapping = {
            "toilet": ["卫生间", "厕所", "洗手间"],
            "food": ["吃的", "美食", "餐厅", "小吃"],
            "bus": ["乘车点", "公交站", "观光车", "停车场"],
            "service": ["游客中心", "服务中心", "咨询处", "医务室"],
        }
        result = [category for category, keywords in mapping.items() if any(keyword in query for keyword in keywords)]
        return result or ["toilet", "food", "bus", "service"]

    @staticmethod
    def _build_recommendation_prompt(query: str, profile: Dict[str, Any]) -> str:
        tags = []
        if profile.get("travel_type") == "family":
            tags.append("亲子")
        if profile.get("avoid_long_walk"):
            tags.append("少走路")
        if profile.get("interests"):
            tags.append("兴趣偏好：" + "、".join(profile.get("interests")))
        if profile.get("time_budget"):
            tags.append("时间预算：" + str(profile.get("time_budget")))
        extra = "；".join(tags)
        return f"{query}。请结合这些偏好给出建议：{extra}" if extra else query

    @staticmethod
    def _guess_last_poi_from_query(query: str, scenic_name: str | None) -> str | None:
        text = query.strip("？?。 ")
        if scenic_name and scenic_name in text:
            text = text.replace(scenic_name, "").strip()
        match = re.search(r"([^\s，。？?]{2,12})(有什么特别|适合拍照|讲的是什么|为什么)", text)
        return match.group(1) if match else None

    def _rewrite_route_guide_answer(
            self,
            req: RoutePlanRequest,
            route_resp: RoutePlanResponse,
    ) -> str:
        data = route_resp.data

        start_name = data.start.name
        end_name = data.end.name
        distance_m = data.summary.total_distance_m
        duration_min = data.summary.total_duration_min
        mode = data.summary.mode
        mode_text = {
            "walk": "步行",
            "drive": "驾车",
            "bike": "骑行",
        }.get(mode, "出行")

        step_text = "\n".join(
            f"{idx + 1}. {step.instruction}（{step.distance_m}米，约{step.duration_min}分钟）"
            for idx, step in enumerate(data.steps[:6])
        )

        scenic_context = "灵山胜境"
        destination_intro = data.end.intro or ""
        arrival_tip = data.arrival_tip or ""

        system_prompt = (
            "你是景区数字人导游。"
            "你的任务是把结构化路线结果改写成适合语音播报的导游式口播。"
            "不要像导航软件逐条念指令。"
            "要像现场导游边带路边讲，语言自然、稳重、简洁。"
            "不要编造路线中不存在的景点，不要加入地图里没有的信息。"
            "可以适度概括路线过程，但不能篡改终点和距离时长。"
        )

        user_prompt = f"""
    景区：{scenic_context}
    游客需求：{req.query or f"从{start_name}到{end_name}怎么走"}
    路线方式：{mode_text}
    起点：{start_name}
    终点：{end_name}
    总距离：{distance_m}米
    预计时长：{duration_min}分钟

    路线步骤：
    {step_text}

    终点介绍：
    {destination_intro}

    到达提示：
    {arrival_tip}

    请改写成一段导游式口播，要求：
    1. 开头要有带领游客出发的感觉；
    2. 中间自然概括怎么走，不要机械逐条念；
    3. 结尾要点出到达后先看什么；
    4. 控制在 120~180 字；
    5. 直接输出口播内容，不要加标题。
    """.strip()

        response = self.llm_client.chat(
            [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt),
            ]
        )

        text = (response.content or "").strip()
        if not text:
            raise ValueError("路线导游改写为空")

        return text

    # =========================
    # 旧路线能力：保留
    # =========================

    def guide_route_plan(self, req: CommandRequest) -> RouterResponse:
        scene_context = {
            "destination_id": req.destination_id,
            "destination_name": req.destination_name,
            "scenic_id": req.scenic_id,
            "scenic_name": req.scenic_name,
            "scope_mode": req.scope_mode,
        }

        route_result = self._load_route_plan(
            query=req.query,
            scene_context=scene_context,
            user_profile=req.user_profile or {},
        )

        route_data = self._normalize_route_data(route_result)
        poi_list = route_data.get("poi_list", [])

        poi_knowledge = self._load_poi_knowledge_for_route(
            poi_list=poi_list,
            query=req.query,
            destination_id=req.destination_id,
            destination_name=req.destination_name,
            scenic_id=req.scenic_id,
            scenic_name=req.scenic_name,
            scope_mode=req.scope_mode,
        )

        narration = self._build_route_narration(
            route_plan=route_data,
            poi_knowledge=poi_knowledge,
            user_profile=req.user_profile or {},
            scenic_name=req.scenic_name or req.destination_name,
        )

        speech_text = narration.get("summary") or route_data.get("summary") or "我已经为您整理好一条游览路线。"

        return RouterResponse(
            intent="guide_route_plan",
            action="show_route_plan",
            speech_text=speech_text,
            ui_command={
                "type": "show_route_plan",
                "route": route_data,
                "narration": narration,
            },
            data={
                "answer_type": "guide_route_plan",
                "query": req.query,
                "route": route_data,
                "poi_knowledge": poi_knowledge,
                "narration": narration,
                "debug": {
                    "scope_mode": req.scope_mode,
                    "destination_name": req.destination_name,
                    "scenic_name": req.scenic_name,
                    "route_source": route_result.get("_route_source", "unknown"),
                },
            },
        )

    def _load_route_plan(
        self,
        query: str,
        scene_context: Dict[str, Any],
        user_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self.route_planner is not None and hasattr(self.route_planner, "plan"):
            try:
                result = self.route_planner.plan(
                    query=query,
                    scene_context=scene_context,
                    user_profile=user_profile,
                )
                if isinstance(result, dict):
                    result["_route_source"] = "route_planner"
                    return result
            except Exception as exc:
                print("route_planner.plan ERROR:", exc)
                traceback.print_exc()

        try:
            result = self.router.handle(
                query=query,
                scene_context=scene_context,
                user_profile=user_profile,
            )
            if isinstance(result, dict):
                result["_route_source"] = "router"
                return result
        except Exception as exc:
            print("router.handle route fallback ERROR:", exc)
            traceback.print_exc()

        return {
            "_route_source": "fallback_empty",
            "summary": "",
            "poi_list": [],
            "segments": [],
            "path_polyline": [],
            "total_walk_minutes": 0,
            "total_distance_meters": 0,
        }

    def _normalize_route_data(self, route_result: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(route_result, dict):
            return {
                "summary": "",
                "poi_list": [],
                "segments": [],
                "path_polyline": [],
                "total_walk_minutes": 0,
                "total_distance_meters": 0,
            }

        data = route_result.get("data")
        if isinstance(data, dict) and isinstance(data.get("route"), dict):
            route = dict(data["route"])
            route.setdefault("summary", data.get("summary", ""))
            return self._finalize_route_data(route)

        if isinstance(route_result.get("route"), dict):
            route = dict(route_result["route"])
            route.setdefault("summary", route_result.get("summary", ""))
            return self._finalize_route_data(route)

        return self._finalize_route_data(route_result)

    def _finalize_route_data(self, route: Dict[str, Any]) -> Dict[str, Any]:
        poi_list = route.get("poi_list") or route.get("pois") or []
        normalized_poi_list: List[Dict[str, Any]] = []

        for index, poi in enumerate(poi_list):
            if not isinstance(poi, dict):
                continue
            normalized_poi_list.append(
                {
                    "poi_id": poi.get("poi_id") or poi.get("id") or f"poi-{index}",
                    "poi_name": poi.get("poi_name") or poi.get("name") or f"点位{index + 1}",
                    "intro": poi.get("intro") or poi.get("summary") or "",
                    "photo_points": poi.get("photo_points") or [],
                    "latitude": poi.get("latitude"),
                    "longitude": poi.get("longitude"),
                    "raw": poi,
                }
            )

        return {
            "route_id": route.get("route_id"),
            "summary": route.get("summary", ""),
            "scenic_area_id": route.get("scenic_area_id") or route.get("scenic_id"),
            "start": route.get("start"),
            "end": route.get("end"),
            "poi_list": normalized_poi_list,
            "segments": route.get("segments", []),
            "path_polyline": route.get("path_polyline", []),
            "total_walk_minutes": route.get("total_walk_minutes", 0),
            "total_distance_meters": route.get("total_distance_meters", 0),
        }

    def _load_poi_knowledge_for_route(
        self,
        poi_list: List[Dict[str, Any]],
        query: str,
        destination_id: str | None,
        destination_name: str | None,
        scenic_id: str | None,
        scenic_name: str | None,
        scope_mode: str,
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []

        for poi in poi_list:
            poi_name = (poi.get("poi_name") or "").strip()
            if not poi_name:
                continue

            try:
                ask_result = self.ask(
                    AskRequest(
                        query=f"{poi_name} {query}".strip(),
                        destination_id=destination_id,
                        destination_name=destination_name,
                        scenic_id=scenic_id,
                        scenic_name=scenic_name,
                        scope_mode=scope_mode,
                    )
                )

                result.append(
                    {
                        "poi_id": poi.get("poi_id"),
                        "poi_name": poi_name,
                        "knowledge_answer": ask_result.answer,
                        "references": self._extract_references(ask_result.answer),
                        "retrieved_contexts": ask_result.retrieved_contexts,
                    }
                )
            except Exception as exc:
                print(f"_load_poi_knowledge_for_route ERROR poi={poi_name}:", exc)
                traceback.print_exc()
                result.append(
                    {
                        "poi_id": poi.get("poi_id"),
                        "poi_name": poi_name,
                        "knowledge_answer": "",
                        "references": [],
                        "retrieved_contexts": [],
                    }
                )

        return result

    def _build_route_narration(
        self,
        route_plan: Dict[str, Any],
        poi_knowledge: List[Dict[str, Any]],
        user_profile: Dict[str, Any],
        scenic_name: str | None = None,
    ) -> Dict[str, Any]:
        poi_list = route_plan.get("poi_list", [])
        if not poi_list:
            return {
                "summary": "当前没有可用路线，我先不给您乱推荐，您可以换个偏好再试试。",
                "steps": [],
            }

        interest_tags = self._extract_interest_tags(user_profile)
        audience = self._infer_audience_from_profile(user_profile)

        steps: List[Dict[str, Any]] = []
        ordered_names: List[str] = []

        for index, poi in enumerate(poi_list, start=1):
            poi_name = poi.get("poi_name") or f"点位{index}"
            ordered_names.append(poi_name)

            matched_knowledge = next(
                (item for item in poi_knowledge if item.get("poi_id") == poi.get("poi_id")),
                None,
            )

            guide_text = self._build_single_poi_route_guide(
                poi=poi,
                knowledge_answer=(matched_knowledge or {}).get("knowledge_answer", ""),
                audience=audience,
                interests=interest_tags,
                scenic_name=scenic_name,
                step_index=index,
            )

            steps.append(
                {
                    "step_index": index,
                    "poi_id": poi.get("poi_id"),
                    "poi_name": poi_name,
                    "guide_text": guide_text,
                }
            )

        summary = self._build_route_summary(
            route_plan=route_plan,
            ordered_names=ordered_names,
            scenic_name=scenic_name,
            interests=interest_tags,
        )

        return {
            "summary": summary,
            "steps": steps,
        }

    def _build_single_poi_route_guide(
        self,
        poi: Dict[str, Any],
        knowledge_answer: str,
        audience: str,
        interests: List[str],
        scenic_name: str | None,
        step_index: int,
    ) -> str:
        poi_name = poi.get("poi_name") or f"点位{step_index}"
        core_knowledge = self._strip_references_section(knowledge_answer).strip()
        core_knowledge = self._compress_text(core_knowledge, max_length=160)

        interest_lines: List[str] = []
        if "历史" in interests:
            interest_lines.append("可以重点讲它的历史背景")
        if "拍照" in interests:
            interest_lines.append("适合提醒游客留意拍照位置")
        if "亲子" in interests:
            interest_lines.append("讲法可以更轻松一点，方便孩子理解")
        if "佛教文化" in interests:
            interest_lines.append("可以突出宗教文化含义")
        if "休闲" in interests:
            interest_lines.append("可以提醒适合停留休息")

        poi_intro = (poi.get("intro") or "").strip()
        photo_points = poi.get("photo_points") or []

        parts: List[str] = [f"第{step_index}站推荐先到{poi_name}。"]

        if scenic_name:
            parts.append(f"它属于{scenic_name}这条游览线里的一个重点点位。")

        if poi_intro:
            parts.append(f"这里的核心看点是：{self._compress_text(poi_intro, max_length=80)}")

        if core_knowledge:
            parts.append(f"现场可以这样讲：{core_knowledge}")

        if photo_points:
            photo_text = "、".join([str(x) for x in photo_points[:3] if str(x).strip()])
            if photo_text:
                parts.append(f"如果游客想拍照，可以提示关注：{photo_text}。")

        if interest_lines:
            parts.append("；".join(interest_lines) + "。")

        text = "".join(parts)
        return self._truncate_text(text, max_length=220 if audience == "general" else 260)

    def _build_route_summary(
        self,
        route_plan: Dict[str, Any],
        ordered_names: List[str],
        scenic_name: str | None,
        interests: List[str],
    ) -> str:
        if not ordered_names:
            return "当前没有可用路线。"

        total_walk_minutes = route_plan.get("total_walk_minutes", 0)
        total_distance_meters = route_plan.get("total_distance_meters", 0)

        interest_text = ""
        if interests:
            interest_text = "，整体更偏向" + "、".join(interests)

        route_names_text = " → ".join(ordered_names[:5])

        scenic_prefix = f"在{scenic_name}里，" if scenic_name else ""
        walk_text = ""
        if total_walk_minutes:
            walk_text += f"步行大约{total_walk_minutes}分钟"
        if total_distance_meters:
            if walk_text:
                walk_text += "，"
            walk_text += f"全程约{total_distance_meters}米"

        if walk_text:
            walk_text = "。" + walk_text + "。"

        return (
            f"{scenic_prefix}我给您整理了一条按游览顺序更自然的路线：{route_names_text}"
            f"{interest_text}{walk_text}"
        ).strip()



    def _rewrite_route_plan_answer(
        self,
        req: RoutePlanRequest,
        route_response: RoutePlanResponse,
    ) -> str:
        scenic_name = {
            "lingshan": "灵山胜境",
        }.get(req.scenic_id, req.scenic_id)

        data = route_response.data
        steps_text = "\n".join(
            [
                f"{idx}. {step.instruction}（约{step.distance_m}米，约{step.duration_min}分钟）"
                for idx, step in enumerate(data.steps[:6], start=1)
            ]
        )
        waypoint_text = "、".join([x.name for x in data.waypoints]) if data.waypoints else "无"
        poi_source = data.debug.get("poi_source", "unknown")

        system_prompt = (
            "你是景区现场导游。"
            "请把结构化路线信息改写成一段适合直接播报的导游式引导词。"
            "要求自然、有人带路的感觉，不要像导航软件，不要逐条机械念步骤。"
            "但要保留真正有用的走法提示，让游客知道大概怎么走。"
            "必须使用中文，不要列点，不要输出标题。"
            "不要说'如果你愿意我还可以'这类系统提示。"
        )

        user_prompt = (
            f"景区：{scenic_name}\n"
            f"用户原始问题：{req.query or ''}\n"
            f"路线模式：{data.summary.mode}\n"
            f"起点：{data.start.name}\n"
            f"终点：{data.end.name}\n"
            f"途经点：{waypoint_text}\n"
            f"总距离：{data.summary.total_distance_m} 米\n"
            f"总时长：{data.summary.total_duration_min} 分钟\n"
            f"终点介绍：{data.end.intro or ''}\n"
            f"路线来源：{poi_source}\n"
            f"关键步骤：\n{steps_text}\n\n"
            "请改写成一段 120 到 220 字左右的导游式路线播报，要求：\n"
            "1. 开头先说明从哪里出发、去哪里、多久能到。\n"
            "2. 中间把路线步骤压缩成 2 到 4 句自然引导，不要逐条硬念每一步。\n"
            "3. 结尾补一句到达后先看什么。\n"
            "4. 语气要像景区导游带路，不要像地图导航。"
        )

        result = self.llm_client.chat(
            [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt),
            ]
        )
        text = (result.content or "").strip()
        if not text:
            raise ValueError("route plan guide rewrite empty")
        return self._truncate_text(text, max_length=240)

    def _build_route_plan_answer_fallback(
        self,
        req: RoutePlanRequest,
        route_response: RoutePlanResponse,
    ) -> str:
        data = route_response.data
        scenic_name = {
            "lingshan": "灵山胜境",
        }.get(req.scenic_id, req.scenic_id)

        step_brief = []
        usable_steps = [step for step in data.steps if (step.instruction or "").strip()]
        for idx, step in enumerate(usable_steps[:4], start=1):
            text = step.instruction.strip("，,。 ")
            if idx == 1:
                step_brief.append(f"先{text}")
            elif idx == len(usable_steps[:4]):
                step_brief.append(f"最后{text}")
            else:
                step_brief.append(f"再{text}")
        route_text = "，".join(step_brief) + "。" if step_brief else ""

        parts: List[str] = []
        parts.append(
            f"您好，您现在从{data.start.name}出发，前往{data.end.name}。"
            f"在{scenic_name}里，这段路全程大约{data.summary.total_distance_m}米，"
            f"正常大概需要{data.summary.total_duration_min}分钟。"
        )
        if route_text:
            parts.append(f"走法上，{route_text}")
        if data.end.intro:
            parts.append(f"到了{data.end.name}之后，建议您先留意：{data.end.intro}")
        return self._truncate_text("".join(parts), max_length=240)

    @staticmethod
    def _build_route_narration_brief(guide_answer: str) -> str:
        text = (guide_answer or "").strip()
        if len(text) <= 120:
            return text
        cut = text[:120]
        last_stop = max(cut.rfind("。"), cut.rfind("！"), cut.rfind("？"))
        if last_stop >= 30:
            return cut[: last_stop + 1]
        return cut.rstrip() + "…"

    def _rewrite_as_guide_answer(
        self,
        question: str,
        knowledge_answer: str,
        style: str,
        audience: str,
        max_length: int,
        include_tips: bool,
        include_next_suggestion: bool,
        scenic_name: str | None = None,
    ) -> str:
        core_text = self._strip_references_section(knowledge_answer).strip()

        style_prompt = {
            "guide": "像景区现场导游一样自然讲解，连贯、口语化、有带领感。",
            "friendly": "像热情朋友带玩一样自然介绍，轻松亲切。",
            "concise": "简洁但有导游感，不要太展开。",
        }.get(style, "像景区现场导游一样自然讲解，连贯、口语化、有带领感。")

        audience_prompt = {
            "general": "面向普通游客，表达自然清楚。",
            "parent_child": "面向亲子游客，表达更容易理解，可以稍微生动一点。",
            "history": "面向历史文化兴趣游客，适当突出文化背景和象征意义。",
            "elder": "面向中老年游客，表达稳一点、清楚一点。",
        }.get(audience, "面向普通游客，表达自然清楚。")

        scenic_prompt = f"当前讲解场景是：{scenic_name}。" if scenic_name else ""

        extra_requirements = []
        if include_tips:
            extra_requirements.append("最后自然补一句现场观察或游览提示。")
        if include_next_suggestion:
            extra_requirements.append("最后自然补一句下一步可以接着看的建议。")

        extra_prompt = "\n".join(extra_requirements) if extra_requirements else "不用额外补充结尾建议。"

        system_prompt = (
            "你是景区数字人导游。"
            "你的任务是把知识库答案改写成适合口播的导游式讲解。"
            "必须忠于原始知识，不要新增知识库里没有的事实。"
            "不要写成1、2、3分点。"
            "不要写成“根据资料”“资料显示”“首先其次最后”这种讲稿腔。"
            "要像导游边走边讲那样自然。"
            "避免书面总结风格。"
        )

        user_prompt = (
            f"用户问题：{question}\n\n"
            f"{scenic_prompt}\n"
            f"知识库原始答案：\n{core_text}\n\n"
            f"风格要求：{style_prompt}\n"
            f"受众要求：{audience_prompt}\n"
            f"补充要求：{extra_prompt}\n\n"
            f"字数控制在 {max_length} 字以内。\n"
            "直接输出最终导游讲解，不要加标题，不要列点，不要解释你怎么改写的。"
        )

        response = self.llm_client.chat(
            [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt),
            ]
        )

        text = (response.content or "").strip()
        if not text:
            raise ValueError("LLM 改写为空")

        return self._truncate_text(text, max_length=max_length)

    def _build_guide_answer_fallback(
        self,
        question: str,
        knowledge_answer: str,
        style: str,
        audience: str,
        max_length: int,
        include_tips: bool,
        include_next_suggestion: bool,
        scenic_name: str | None = None,
    ) -> str:
        core_text = self._strip_references_section(knowledge_answer).strip()
        core_text = re.sub(r"\n{2,}", "\n", core_text).strip()

        if not core_text:
            core_text = "这个问题我先给您简单介绍一下。"

        core_text = re.sub(r"^\d+\.\s*", "", core_text, flags=re.M)
        core_text = core_text.replace("**", "")

        if style == "concise":
            prefix = "简单来说，"
        elif style == "friendly":
            prefix = "我给您轻松讲讲，"
        else:
            prefix = "我给您像现场讲解一样说一下，"

        if audience == "parent_child":
            audience_prefix = "如果您是带孩子一起看，可以这样理解："
        elif audience == "history":
            audience_prefix = "如果从历史文化角度看，重点在于："
        elif audience == "elder":
            audience_prefix = "我尽量说得更清楚一点，您重点听这里："
        else:
            audience_prefix = ""

        parts: List[str] = []
        opening = prefix
        if scenic_name:
            opening += f"在{scenic_name}里，"
        parts.append(opening)

        if audience_prefix:
            parts.append(audience_prefix)

        parts.append(core_text)

        if include_tips:
            parts.append("您到现场时，可以重点留意它背后的象征意义和细节。")

        if include_next_suggestion:
            parts.append("如果您愿意，我还可以继续给您接着讲它周边值得一起看的点位。")

        text = "".join(parts)
        return self._truncate_text(text, max_length=max_length)

    def _extract_interest_tags(self, user_profile: Dict[str, Any]) -> List[str]:
        tags: List[str] = []

        for key in ["interests", "interest_tags", "tags"]:
            value = user_profile.get(key)
            if isinstance(value, list):
                tags.extend([str(x).strip() for x in value if str(x).strip()])
            elif isinstance(value, str) and value.strip():
                tags.extend([x.strip() for x in re.split(r"[,，/、\s]+", value) if x.strip()])

        ordered: List[str] = []
        seen = set()
        for tag in tags:
            if tag not in seen:
                ordered.append(tag)
                seen.add(tag)
        return ordered

    @staticmethod
    def _infer_audience_from_profile(user_profile: Dict[str, Any]) -> str:
        audience = str(user_profile.get("audience") or "").strip()
        if audience:
            return audience

        tags = user_profile.get("interests") or []
        tag_text = " ".join([str(x) for x in tags])

        if "亲子" in tag_text:
            return "parent_child"
        if "历史" in tag_text or "文化" in tag_text:
            return "history"
        return "general"

    @staticmethod
    def _compress_text(text: str, max_length: int) -> str:
        text = re.sub(r"\s+", " ", (text or "")).strip()
        if len(text) <= max_length:
            return text
        return text[: max_length - 1].rstrip() + "…"

    @staticmethod
    def _strip_references_section(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"参考片段[:：].*$", "", text, flags=re.S).strip()
        return text

    @staticmethod
    def _extract_references(text: str) -> List[str]:
        if not text:
            return []

        match = re.search(r"参考片段[:：]\s*(.+)$", text, flags=re.S)
        if not match:
            return []

        raw = match.group(1).strip()
        if not raw:
            return []

        refs = [item.strip() for item in raw.split(",") if item.strip()]
        return refs

    @staticmethod
    def _truncate_text(text: str, max_length: int) -> str:
        text = (text or "").strip()
        if len(text) <= max_length:
            return text
        if max_length <= 1:
            return text[:max_length]
        return text[: max_length - 1].rstrip() + "…"

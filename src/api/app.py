from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from api.travel_guide_search_api import router as travel_guide_search_router

from api.schemas import (
    ASRResponse,
    AskRequest,
    AskResponse,
    CommandRequest,
    GuideChatRequest,
    GuideChatResponse,
    GuideAnswerRequest,
    GuideAnswerResponse,
    HealthResponse,
    MemoryClearResponse,
    NearbyRequest,
    NearbyResponse,
    PoiImportResponse,
    RoutePlanRequest,
    RoutePlanResponse,
    RouterResponse,
    TTSRequest,
    TTSResponse,
    UIEventRequest,
    VoiceCommandResponse,
)
from config import get_settings
from services.guide_api_service import GuideAPIService

logger = logging.getLogger(__name__)


def _raise_as_http_error(prefix: str, exc: Exception) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.exception("%s: %s", prefix, exc)
    raise HTTPException(status_code=500, detail=f"{prefix}: {exc}") from exc


async def _read_wav_upload(file: UploadFile, invalid_suffix_message: str) -> tuple[bytes, str]:
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="上传的音频为空")

    suffix = Path(file.filename or "audio.wav").suffix.lower() or ".wav"
    if suffix != ".wav":
        raise HTTPException(status_code=400, detail=invalid_suffix_message)
    return audio_bytes, suffix


def _parse_user_profile(user_profile: str) -> dict[str, Any]:
    try:
        parsed = json.loads(user_profile or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="user_profile 必须是合法 JSON 字符串") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="user_profile 必须是 JSON 对象")
    return parsed


def build_app(
    *,
    settings: Any | None = None,
    guide_service: GuideAPIService | None = None,
) -> FastAPI:
    app = FastAPI(title="Scenic Guide API", version="1.0.0", docs_url="/docs", redoc_url="/redoc")

    resolved_settings = settings or get_settings()
    resolved_guide_service = guide_service or GuideAPIService(resolved_settings)
    app.state.settings = resolved_settings
    app.state.guide_service = resolved_guide_service
    app.include_router(travel_guide_search_router)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.post("/api/v1/guide/ask", response_model=AskResponse)
    def ask(req: AskRequest) -> AskResponse:
        try:
            return app.state.guide_service.ask(req)
        except Exception as exc:
            _raise_as_http_error("问答失败", exc)

    @app.post("/api/v1/guide/guide-answer", response_model=GuideAnswerResponse)
    def guide_answer(req: GuideAnswerRequest) -> GuideAnswerResponse:
        try:
            return app.state.guide_service.guide_answer(req)
        except Exception as exc:
            _raise_as_http_error("导游式回答失败", exc)

    @app.post("/api/v1/guide/command", response_model=RouterResponse)
    def command(req: CommandRequest) -> RouterResponse:
        try:
            return app.state.guide_service.command(req)
        except Exception as exc:
            _raise_as_http_error("指令处理失败", exc)

    @app.post("/api/v1/guide/route-plan", response_model=RoutePlanResponse)
    def route_plan(req: RoutePlanRequest) -> RoutePlanResponse:
        try:
            return app.state.guide_service.route_plan(req)
        except Exception as exc:
            _raise_as_http_error("路线规划失败", exc)

    @app.post("/api/v1/guide/chat", response_model=GuideChatResponse)
    def chat(req: GuideChatRequest) -> GuideChatResponse:
        try:
            return app.state.guide_service.chat(req)
        except Exception as exc:
            _raise_as_http_error("统一导游回答失败", exc)

    @app.delete("/api/v1/guide/memory/{session_id}", response_model=MemoryClearResponse)
    def clear_memory(session_id: str) -> MemoryClearResponse:
        try:
            app.state.guide_service.clear_memory(session_id)
            return MemoryClearResponse(session_id=session_id, cleared=True, message="memory cleared")
        except Exception as exc:
            _raise_as_http_error("清除会话记忆失败", exc)

    @app.post("/api/v1/guide/poi/import", response_model=PoiImportResponse)
    async def import_poi_file(
        file: UploadFile = File(...),
        scenic_id: str = Form(...),
        scenic_name: str | None = Form(default=None),
        overwrite: bool = Form(default=True),
        use_tencent_geocode: bool = Form(default=True),
        city: str | None = Form(default=None),
        address_hint: str | None = Form(default=None),
    ) -> PoiImportResponse:
        try:
            return await app.state.guide_service.import_poi_file(
                file=file,
                scenic_id=scenic_id,
                scenic_name=scenic_name,
                overwrite=overwrite,
                use_tencent_geocode=use_tencent_geocode,
                city=city,
                address_hint=address_hint,
            )
        except Exception as exc:
            _raise_as_http_error("POI 导入失败", exc)

    @app.post("/api/v1/guide/nearby", response_model=NearbyResponse)
    def nearby(req: NearbyRequest) -> NearbyResponse:
        try:
            return app.state.guide_service.search_nearby(req)
        except Exception as exc:
            _raise_as_http_error("附近设施查询失败", exc)

    @app.post("/api/v1/guide/ui-event", response_model=RouterResponse)
    def ui_event(req: UIEventRequest) -> RouterResponse:
        try:
            return app.state.guide_service.ui_event(req)
        except Exception as exc:
            _raise_as_http_error("UI 事件处理失败", exc)

    @app.post("/api/v1/guide/tts", response_model=TTSResponse)
    def tts(req: TTSRequest) -> TTSResponse:
        try:
            text = (req.text or "").strip()
            if not text:
                raise HTTPException(status_code=400, detail="text 不能为空")

            audio_format = (req.audio_format or "mp3").strip().lower()
            audio_bytes = app.state.guide_service.tts_service.synthesize_bytes(
                text=text,
                voice=req.voice,
                speed=req.speed,
                volume=req.volume,
                pitch=req.pitch,
                audio_format=audio_format,
            )
            if isinstance(audio_bytes, bytearray):
                audio_bytes = bytes(audio_bytes)
            if not isinstance(audio_bytes, bytes):
                raise HTTPException(status_code=500, detail=f"TTS 返回类型错误: {type(audio_bytes)}")
            if not audio_bytes:
                raise HTTPException(status_code=500, detail="TTS 返回为空音频")

            content_type = app.state.guide_service.tts_service.get_content_type(audio_format)
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
            return TTSResponse(
                provider="xfyun",
                text=text,
                voice=req.voice,
                content_type=content_type,
                audio_base64=audio_base64,
            )
        except Exception as exc:
            _raise_as_http_error("TTS 失败", exc)

    @app.post("/api/v1/guide/asr", response_model=ASRResponse)
    async def asr(file: UploadFile = File(...)) -> ASRResponse:
        try:
            audio_bytes, suffix = await _read_wav_upload(
                file=file,
                invalid_suffix_message="当前语音识别接口仅支持 wav 文件，请上传 16k PCM wav。",
            )
            text = app.state.guide_service.asr_service.transcribe_bytes(audio_bytes=audio_bytes, suffix=suffix)
            return ASRResponse(text=text, provider="xfyun", file_name=file.filename, content_type=file.content_type)
        except Exception as exc:
            _raise_as_http_error("语音识别失败", exc)

    @app.post("/api/v1/guide/voice-command", response_model=VoiceCommandResponse)
    async def voice_command(
        file: UploadFile = File(...),
        destination_id: str | None = Form(default=None),
        destination_name: str | None = Form(default=None),
        scenic_id: str | None = Form(default=None),
        scenic_name: str | None = Form(default=None),
        scope_mode: str = Form(default="current_only"),
        user_profile: str = Form(default="{}"),
        with_tts: bool = Form(default=True),
        voice: str = Form(default="xiaolu"),
    ) -> VoiceCommandResponse:
        try:
            audio_bytes, suffix = await _read_wav_upload(
                file=file,
                invalid_suffix_message="当前 voice-command 仅支持 wav 文件，请上传 16k PCM wav。",
            )
            parsed_user_profile = _parse_user_profile(user_profile)
            return app.state.guide_service.voice_command(
                audio_bytes=audio_bytes,
                file_suffix=suffix,
                destination_id=destination_id,
                destination_name=destination_name,
                scenic_id=scenic_id,
                scenic_name=scenic_name,
                scope_mode=scope_mode,
                user_profile=parsed_user_profile,
                with_tts=with_tts,
                voice=voice,
            )
        except Exception as exc:
            _raise_as_http_error("voice-command 失败", exc)

    return app


app = build_app()

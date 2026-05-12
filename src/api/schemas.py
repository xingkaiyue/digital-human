from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    query: str = Field(..., description="用户问题")
    destination_id: Optional[str] = None
    destination_name: Optional[str] = None
    scenic_id: Optional[str] = None
    scenic_name: Optional[str] = None
    scope_mode: str = Field(default="current_only")


class RetrievedContextItem(BaseModel):
    text: str
    metadata: Dict[str, Any]
    distance: float
    score: float


class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    retrieved_contexts: List[RetrievedContextItem]


class GuideAnswerRequest(BaseModel):
    query: str = Field(..., description="用户问题")
    destination_id: Optional[str] = None
    destination_name: Optional[str] = None
    scenic_id: Optional[str] = None
    scenic_name: Optional[str] = None
    scope_mode: str = Field(default="current_only")
    style: Literal["guide", "friendly", "concise"] = Field(default="guide", description="导游式回答风格")
    audience: Literal["general", "parent_child", "history", "elder"] = Field(default="general", description="面向人群")
    max_length: int = Field(default=400, ge=80, le=1200, description="导游式回答最大长度")
    include_tips: bool = Field(default=True, description="是否加入游览提示")
    include_next_suggestion: bool = Field(default=True, description="是否加入下一步建议")


class GuideAnswerResponse(BaseModel):
    question: str
    knowledge_answer: str
    guide_answer: str
    model: str
    references: List[str] = Field(default_factory=list)
    retrieved_contexts: List[RetrievedContextItem] = Field(default_factory=list)
    style: str
    audience: str
    debug: Dict[str, Any] = Field(default_factory=dict)


class CommandRequest(BaseModel):
    query: str
    destination_id: Optional[str] = None
    destination_name: Optional[str] = None
    scenic_id: Optional[str] = None
    scenic_name: Optional[str] = None
    scope_mode: str = Field(default="current_only")
    user_profile: Dict[str, Any] = Field(default_factory=dict)


class UIEventRequest(BaseModel):
    event_type: str
    page_id: str
    destination_id: Optional[str] = None
    destination_name: Optional[str] = None
    scenic_id: Optional[str] = None
    scenic_name: Optional[str] = None
    scope_mode: str = Field(default="current_only")
    user_profile: Dict[str, Any] = Field(default_factory=dict)


class RouterResponse(BaseModel):
    intent: str
    action: str
    speech_text: str
    ui_command: Dict[str, Any]
    data: Dict[str, Any]


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, description="要合成的文本")
    voice: str = Field(default="xiaolu", description="发音人，可用：xiaolu / lingfeizhe")
    speed: int = Field(default=50, ge=0, le=100, description="语速")
    volume: int = Field(default=50, ge=0, le=100, description="音量")
    pitch: int = Field(default=50, ge=0, le=100, description="音高")
    audio_format: Literal["mp3", "wav", "pcm", "raw"] = Field(default="mp3", description="音频格式")


class TTSResponse(BaseModel):
    provider: str = "xfyun"
    text: str
    voice: str
    content_type: str
    audio_base64: str


class VoiceCommandResponse(BaseModel):
    recognized_text: str
    intent: str
    action: str
    speech_text: str
    ui_command: Dict[str, Any]
    data: Dict[str, Any]
    tts: Optional[TTSResponse] = None


class ASRResponse(BaseModel):
    text: str
    provider: str = "xfyun"
    file_name: Optional[str] = None
    content_type: Optional[str] = None


class HealthResponse(BaseModel):
    status: str = "ok"


class LocationPoint(BaseModel):
    lat: float
    lng: float


class RouteNode(BaseModel):
    poi_id: str
    name: str
    lat: float
    lng: float
    point_type: str = Field(default="poi")
    stay_minutes: Optional[int] = None
    intro: Optional[str] = None


class RoutePlanStep(BaseModel):
    seq_no: int
    instruction: str
    distance_m: int = 0
    duration_min: int = 0


class RoutePlanSummary(BaseModel):
    total_distance_m: int
    total_duration_min: int
    mode: str = "walk"


class RoutePlanData(BaseModel):
    scenic_id: str
    start: RouteNode
    end: RouteNode
    waypoints: List[RouteNode] = Field(default_factory=list)
    route_nodes: List[RouteNode] = Field(default_factory=list)
    polyline: List[LocationPoint] = Field(default_factory=list)
    steps: List[RoutePlanStep] = Field(default_factory=list)
    summary: RoutePlanSummary
    narration: str = Field(default="", description="简短路线播报")
    guide_answer: str = Field(default="", description="导游式完整路线讲解")
    arrival_tip: str = Field(default="", description="到达后的游览提示")
    map_pois: List[RouteNode] = Field(default_factory=list)
    debug: Dict[str, Any] = Field(default_factory=dict)


class RoutePlanRequest(BaseModel):
    session_id: str = Field(..., description="Session id")
    scenic_id: str = Field(..., description="Scenic area id")
    query: Optional[str] = Field(default=None, description="原始用户问句，可用于日志和导游话术")
    mode: Literal["walk", "drive", "bike"] = Field(default="walk", description="路线模式")
    start_poi: Optional[str] = Field(default=None, description="起点 POI 名称或 ID")
    end_poi: Optional[str] = Field(default=None, description="终点 POI 名称或 ID")
    current_location: Optional[LocationPoint] = Field(default=None, description="当前定位；没有 start_poi 时可使用")
    waypoints: List[str] = Field(default_factory=list, description="途经点名称或 ID")
    interests: List[str] = Field(default_factory=list, description="兴趣标签")
    max_walk_minutes: Optional[int] = Field(default=None, ge=1, description="最大步行时长")
    avoid_stairs: bool = Field(default=False)
    family_friendly: bool = Field(default=False)


class RoutePlanResponse(BaseModel):
    intent: str = "route_plan"
    action: str = "show_route"
    message: str
    data: RoutePlanData
    ui_command: Optional[Dict[str, Any]] = None


class PoiItem(BaseModel):
    poi_id: str
    name: str
    aliases: List[str] = Field(default_factory=list)
    lat: float
    lng: float
    point_type: str = Field(default="poi")
    stay_minutes: int = Field(default=10)
    intro: str = Field(default="")
    address: str = Field(default="")
    tags: List[str] = Field(default_factory=list)
    source: str = Field(default="unknown")
    geocode_status: Literal["original", "tencent_resolved", "failed", "skipped"] = Field(default="skipped")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class PoiImportResponse(BaseModel):
    scenic_id: str
    scenic_name: Optional[str] = None
    poi_count: int
    pois: List[PoiItem] = Field(default_factory=list)
    invalid_count: int = 0
    invalid_items: List[Dict[str, Any]] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
    message: str


class PoiListResponse(BaseModel):
    scenic_id: str
    scenic_name: Optional[str] = None
    poi_count: int
    pois: List[PoiItem] = Field(default_factory=list)


class NearbyRequest(BaseModel):
    scenic_id: str
    center_poi: Optional[str] = None
    current_location: Optional[LocationPoint] = None
    categories: List[Literal["toilet", "food", "bus", "service"]] = Field(default_factory=list)
    radius_m: int = Field(default=500, ge=50, le=5000)
    limit: int = Field(default=10, ge=1, le=50)


class NearbyPoiItem(BaseModel):
    name: str
    address: str = ""
    lat: float
    lng: float
    distance_m: int = 0
    category: str
    source: str
    poi_id: Optional[str] = None
    point_type: Optional[str] = None


class NearbyResponse(BaseModel):
    scenic_id: str
    center: Dict[str, Any]
    radius_m: int
    results: Dict[str, List[NearbyPoiItem]] = Field(default_factory=dict)
    ui_command: Dict[str, Any] = Field(default_factory=dict)
    message: str
    debug: Dict[str, Any] = Field(default_factory=dict)


class MemoryTurn(BaseModel):
    query: str
    intent: str = ""
    answer: str = ""
    timestamp: str


class ConversationMemory(BaseModel):
    session_id: str
    turns: List[MemoryTurn] = Field(default_factory=list)
    profile: Dict[str, Any] = Field(default_factory=dict)
    last_poi: Optional[str] = None
    last_route: Dict[str, Any] = Field(default_factory=dict)
    last_intent: str = ""
    summary: str = ""


class GuideChatRequest(BaseModel):
    session_id: str
    query: str
    scenic_id: Optional[str] = None
    scenic_name: Optional[str] = None
    destination_id: Optional[str] = None
    destination_name: Optional[str] = None
    scope_mode: str = Field(default="current_only")
    current_location: Optional[LocationPoint] = None
    page_id: Optional[str] = None
    user_profile: Dict[str, Any] = Field(default_factory=dict)
    with_memory: bool = True
    with_tts: bool = False


class GuideChatResponse(BaseModel):
    session_id: str
    intent: str
    action: str
    answer: str
    speech_text: str
    ui_command: Dict[str, Any] = Field(default_factory=dict)
    data: Dict[str, Any] = Field(default_factory=dict)
    memory: Dict[str, Any] = Field(default_factory=dict)
    debug: Dict[str, Any] = Field(default_factory=dict)


class MemoryClearResponse(BaseModel):
    session_id: str
    cleared: bool = True
    message: str = "memory cleared"

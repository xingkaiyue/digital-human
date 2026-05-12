from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from config import get_settings
from services.travel_guide_search_service import TravelGuideSearchService


router = APIRouter(prefix="/api/v1/travel-guides", tags=["travel-guides"])


class TravelGuideSearchRequest(BaseModel):
    destination: Optional[str] = Field(
        default=None,
        description="景区或目的地名称，例如：灵山胜境",
    )
    city: Optional[str] = Field(
        default=None,
        description="城市，例如：无锡",
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="附加攻略关键词，例如：亲子、一日游、路线、拍照",
    )
    query: Optional[str] = Field(
        default=None,
        description="游客自定义搜索词；如果传了 query，则优先使用 query 搜索",
    )

    num: int = Field(default=10, ge=1, le=10, description="返回数量，范围 1-10")
    only_preferred_sites: bool = Field(
        default=False,
        description="是否限制在常见旅游攻略平台内搜索",
    )

    @model_validator(mode="after")
    def validate_search_condition(self) -> "TravelGuideSearchRequest":
        has_query = bool((self.query or "").strip())
        has_destination = bool((self.destination or "").strip())

        if not has_query and not has_destination:
            raise ValueError("query 和 destination 至少传一个")

        return self


class TravelGuideSearchItemResponse(BaseModel):
    position: int = 0
    title: str = ""
    link: str = ""
    snippet: str = ""
    source: str = ""
    displayed_link: str = ""
    thumbnail: str = ""
    result_type: str = "article"


class TravelGuideSearchResponse(BaseModel):
    mode: str
    destination: str = ""
    city: str = ""
    query: str
    count: int
    results: List[TravelGuideSearchItemResponse] = Field(default_factory=list)
    search_metadata: Dict[str, Any] = Field(default_factory=dict)


@router.post("/search", response_model=TravelGuideSearchResponse)
def search_travel_guides(req: TravelGuideSearchRequest) -> TravelGuideSearchResponse:
    try:
        settings = get_settings()
        service = TravelGuideSearchService(settings)

        result = service.search_guides(
            destination=req.destination,
            city=req.city,
            query=req.query,
            keywords=req.keywords,
            num=req.num,
            only_preferred_sites=req.only_preferred_sites,
        )

        return TravelGuideSearchResponse(**result)

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except Exception as exc:
        raise HTTPException(status_code=500, detail="旅游攻略搜索失败: " + str(exc)) from exc

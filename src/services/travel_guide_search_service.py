from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from config import AppSettings


@dataclass
class TravelGuideSearchItem:
    position: int
    title: str
    link: str
    snippet: str
    source: str = ""
    displayed_link: str = ""
    thumbnail: str = ""
    result_type: str = "article"


class TravelGuideSearchService:
    DEFAULT_GUIDE_WORDS = [
        "旅游攻略",
        "游玩攻略",
        "一日游",
        "游玩路线",
        "门票",
        "开放时间",
        "交通",
        "注意事项",
    ]

    PREFERRED_SITES = [
        "mafengwo.cn",
        "ctrip.com",
        "qunar.com",
        "tripadvisor.cn",
        "xiaohongshu.com",
        "dianping.com",
        "bilibili.com",
    ]

    VIDEO_DOMAINS = [
        "youtube.com",
        "youtu.be",
        "bilibili.com",
        "douyin.com",
        "ixigua.com",
        "kuaishou.com",
    ]

    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.api_key = settings.serpapi_api_key
        self.base_url = settings.serpapi_base_url
        self.timeout = settings.serpapi_timeout_seconds
        self.default_num = settings.serpapi_default_num
        self.hl = settings.serpapi_hl
        self.gl = settings.serpapi_gl

    def search_guides(
        self,
        *,
        destination: Optional[str] = None,
        city: Optional[str] = None,
        query: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        num: Optional[int] = None,
        only_preferred_sites: bool = False,
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("SerpApi 未配置，请在 .env 中设置 SERPAPI_API_KEY")

        final_num = max(1, min(int(num or self.default_num), 10))

        final_query = self._resolve_query(
            destination=destination,
            city=city,
            query=query,
            keywords=keywords or [],
            only_preferred_sites=only_preferred_sites,
        )

        payload = self._request_serpapi(query=final_query, num=final_num)
        results = self._parse_results(payload=payload, limit=final_num)

        return {
            "mode": "custom_search" if query else "default_destination_guides",
            "destination": destination or "",
            "city": city or "",
            "query": final_query,
            "count": len(results),
            "results": [item.__dict__ for item in results],
            "search_metadata": payload.get("search_metadata") or {},
        }

    def _resolve_query(
        self,
        *,
        destination: Optional[str],
        city: Optional[str],
        query: Optional[str],
        keywords: List[str],
        only_preferred_sites: bool,
    ) -> str:
        custom_query = self._clean_text(query)

        if custom_query:
            return self._apply_site_filter(custom_query, only_preferred_sites)

        destination_text = self._clean_text(destination)
        city_text = self._clean_text(city)

        if not destination_text:
            raise ValueError("默认搜索模式下 destination 不能为空；如果是游客自由搜索，请传 query")

        clean_keywords = []
        for item in keywords:
            text = self._clean_text(str(item or ""))
            if text:
                clean_keywords.append(text)

        parts = []
        if city_text:
            parts.append(city_text)

        parts.append(destination_text)

        if clean_keywords:
            parts.extend(clean_keywords)
            parts.append("旅游攻略")
        else:
            parts.extend(self.DEFAULT_GUIDE_WORDS)

        final_query = " ".join(parts)
        return self._apply_site_filter(final_query, only_preferred_sites)

    def _apply_site_filter(self, query: str, only_preferred_sites: bool) -> str:
        query = self._normalize_query(query)

        if not only_preferred_sites:
            return query

        site_filter = " OR ".join("site:" + site for site in self.PREFERRED_SITES)
        return query + " (" + site_filter + ")"

    def _request_serpapi(self, query: str, num: int) -> Dict[str, Any]:
        params = {
            "engine": "google",
            "q": query,
            "api_key": self.api_key,
            "num": num,
            "hl": self.hl,
            "gl": self.gl,
            "safe": "active",
        }

        try:
            response = requests.get(
                self.base_url,
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise RuntimeError("SerpApi 请求失败: " + str(exc)) from exc

        if response.status_code != 200:
            raise RuntimeError(
                "SerpApi 返回错误，status="
                + str(response.status_code)
                + ", detail="
                + response.text[:500]
            )

        payload = response.json()

        if payload.get("error"):
            raise RuntimeError("SerpApi error: " + str(payload.get("error")))

        return payload

    def _parse_results(
        self,
        payload: Dict[str, Any],
        limit: int,
    ) -> List[TravelGuideSearchItem]:
        items: List[TravelGuideSearchItem] = []
        seen_links = set()

        # 1. 普通网页搜索结果。很多旅游攻略文章都在这里。
        for raw in payload.get("organic_results") or []:
            item = self._build_item_from_organic(raw, fallback_position=len(items) + 1)
            if not item:
                continue
            if item.link in seen_links:
                continue

            seen_links.add(item.link)
            items.append(item)

            if len(items) >= limit:
                return items

        # 2. Google 页面中偶尔会出现 inline_videos。
        # SerpApi 会把它们解析到 inline_videos。
        for raw in payload.get("inline_videos") or []:
            item = self._build_item_from_inline_video(raw, fallback_position=len(items) + 1)
            if not item:
                continue
            if item.link in seen_links:
                continue

            seen_links.add(item.link)
            items.append(item)

            if len(items) >= limit:
                return items

        return items

    def _build_item_from_organic(
        self,
        raw: Dict[str, Any],
        fallback_position: int,
    ) -> Optional[TravelGuideSearchItem]:
        link = raw.get("link") or ""
        if not link:
            return None

        thumbnail = raw.get("thumbnail") or ""
        result_type = self._guess_result_type(link=link, thumbnail=thumbnail)

        return TravelGuideSearchItem(
            position=int(raw.get("position") or fallback_position),
            title=raw.get("title") or "",
            link=link,
            snippet=raw.get("snippet") or "",
            source=raw.get("source") or "",
            displayed_link=raw.get("displayed_link") or "",
            thumbnail=thumbnail,
            result_type=result_type,
        )

    def _build_item_from_inline_video(
        self,
        raw: Dict[str, Any],
        fallback_position: int,
    ) -> Optional[TravelGuideSearchItem]:
        link = raw.get("link") or ""
        if not link:
            return None

        return TravelGuideSearchItem(
            position=fallback_position,
            title=raw.get("title") or "",
            link=link,
            snippet=raw.get("date") or raw.get("channel") or raw.get("platform") or "",
            source=raw.get("platform") or raw.get("channel") or "",
            displayed_link=raw.get("platform") or "",
            thumbnail=raw.get("thumbnail") or "",
            result_type="video",
        )

    def _guess_result_type(self, link: str, thumbnail: str) -> str:
        link_lower = link.lower()

        for domain in self.VIDEO_DOMAINS:
            if domain in link_lower:
                return "video"

        if thumbnail:
            return "image"

        return "article"

    @staticmethod
    def _clean_text(text: Optional[str]) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    @staticmethod
    def _normalize_query(query: str) -> str:
        return re.sub(r"\s+", " ", query or "").strip()

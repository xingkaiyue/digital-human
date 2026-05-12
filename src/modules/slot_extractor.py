from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SlotExtractionResult:
    slots: Dict[str, Any] = field(default_factory=dict)
    missing_slots: List[str] = field(default_factory=list)
    debug: Dict[str, Any] = field(default_factory=dict)


class SlotExtractor:
    """
    负责从用户问题中抽取结构化槽位。
    当前以规则为主，后续可以替换成 LLM / 小模型槽位抽取。
    """

    DEFAULT_SCENIC_ALIASES = {
        "灵山胜境": ["灵山胜境", "灵山", "灵山核心区", "灵山核心景区"],
        "拈花湾禅意小镇": ["拈花湾", "拈花湾禅意小镇", "禅意小镇", "拈花湾小镇"],
    }

    CROWD_KEYWORDS = {
        "family": ["亲子", "带孩子", "小朋友", "儿童", "家庭出游", "一家人"],
        "elderly": ["老人", "长辈", "爸妈", "父母", "老年人"],
        "couple": ["情侣", "约会", "两个人", "恋人"],
        "solo": ["一个人", "独自", "自己逛", "单人"],
        "friends": ["朋友", "闺蜜", "兄弟", "同学", "几个人一起"],
        "photography": ["拍照", "摄影", "出片", "打卡", "拍写真"],
    }

    TIME_BUDGET_KEYWORDS = {
        "2_hours": ["2小时", "两小时"],
        "3_hours": ["3小时", "三小时"],
        "4_hours": ["4小时", "四小时"],
        "half_day": ["半天", "半日"],
        "1_day": ["1天", "一天", "全天"],
        "evening": ["晚上", "夜游", "傍晚"],
        "morning": ["上午", "早上"],
        "afternoon": ["下午"],
    }

    PREFERENCE_KEYWORDS = {
        "culture": ["历史", "文化", "佛教", "讲解", "人文", "艺术"],
        "photo": ["拍照", "摄影", "出片", "打卡"],
        "relax": ["轻松", "休闲", "不累", "慢慢逛", "放松"],
        "pray": ["祈福", "礼佛", "求平安", "许愿"],
        "performance": ["演出", "表演", "秀", "吉祥颂", "九龙灌浴"],
        "food": ["吃饭", "美食", "素斋", "餐厅", "小吃"],
        "kids": ["亲子", "儿童", "小朋友", "互动"],
    }

    ROUTE_PATTERNS = [
        re.compile(
            r"从(?P<start>.+?)(到|去|前往)(?P<end>.+?)(怎么走|怎么去|怎么过去|路线|走法|导航|怎么坐车|怎么过去呢)",
            re.IGNORECASE,
        ),
        re.compile(
            r"去(?P<end>.+?)(怎么走|怎么去|路线|走法|导航|怎么过去)",
            re.IGNORECASE,
        ),
        re.compile(
            r"到(?P<end>.+?)(怎么走|怎么去|路线|走法|导航|怎么过去)",
            re.IGNORECASE,
        ),
    ]

    KNOWLEDGE_SPOT_PATTERNS = [
        re.compile(r"(?P<spot>.+?)是什么"),
        re.compile(r"(?P<spot>.+?)在哪里"),
        re.compile(r"介绍一下(?P<spot>.+)"),
        re.compile(r"(?P<spot>.+?)介绍"),
        re.compile(r"(?P<spot>.+?)几点"),
        re.compile(r"(?P<spot>.+?)开放吗"),
    ]

    def __init__(self, scenic_aliases: Optional[Dict[str, List[str]]] = None):
        self.scenic_aliases = scenic_aliases or self.DEFAULT_SCENIC_ALIASES

    def extract(
        self,
        query: str,
        intent: str,
        scene_context: Optional[Any] = None,
    ) -> SlotExtractionResult:
        text = (query or "").strip()
        result = SlotExtractionResult()

        if not text:
            result.missing_slots.append("query")
            return result

        scenic_name = self._extract_scenic_name(text, scene_context)
        if scenic_name:
            result.slots["scenic_name"] = scenic_name

        crowd_type = self._extract_by_keywords(text, self.CROWD_KEYWORDS)
        if crowd_type:
            result.slots["crowd_type"] = crowd_type

        time_budget = self._extract_by_keywords(text, self.TIME_BUDGET_KEYWORDS)
        if time_budget:
            result.slots["time_budget"] = time_budget

        preference = self._extract_multi_keywords(text, self.PREFERENCE_KEYWORDS)
        if preference:
            result.slots["preference"] = preference

        if intent == "route":
            route_slots = self._extract_route_slots(text)
            result.slots.update(route_slots)
            if not result.slots.get("end_name"):
                result.missing_slots.append("end_name")

        elif intent == "knowledge":
            spot_name = self._extract_knowledge_spot_name(text)
            if spot_name:
                result.slots["spot_name"] = spot_name

        elif intent == "recommend":
            route_style = self._extract_route_style(text)
            if route_style:
                result.slots["route_style"] = route_style

        result.debug = {
            "normalized_query": self._normalize(text),
            "intent": intent,
        }
        return result

    def _extract_scenic_name(self, text: str, scene_context: Optional[Any]) -> Optional[str]:
        for standard_name, aliases in self.scenic_aliases.items():
            for alias in aliases:
                if alias and alias in text:
                    return standard_name

        context_scenic_name = self._ctx_get(scene_context, "scenic_name")
        if context_scenic_name:
            return context_scenic_name

        return None

    def _extract_route_slots(self, text: str) -> Dict[str, str]:
        for pattern in self.ROUTE_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue

            start = (match.groupdict().get("start") or "").strip(" ，,。？?！!")
            end = (match.groupdict().get("end") or "").strip(" ，,。？?！!")

            slots: Dict[str, str] = {}
            if start:
                slots["start_name"] = start
            if end:
                slots["end_name"] = end
            return slots

        return {}

    def _extract_knowledge_spot_name(self, text: str) -> Optional[str]:
        for pattern in self.KNOWLEDGE_SPOT_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue

            spot = (match.groupdict().get("spot") or "").strip(" ，,。？?！!")
            if not spot:
                continue

            # 过滤掉太泛的词
            if spot in {"景点", "路线", "门票", "开放时间"}:
                continue
            return spot

        return None

    def _extract_route_style(self, text: str) -> Optional[str]:
        if "亲子" in text or "带孩子" in text:
            return "family"
        if "老人" in text or "长辈" in text:
            return "elderly"
        if "情侣" in text or "约会" in text:
            return "couple"
        if "拍照" in text or "摄影" in text:
            return "photo"
        if "文化" in text or "历史" in text:
            return "culture"
        if "轻松" in text or "不累" in text:
            return "relax"
        return None

    def _extract_by_keywords(self, text: str, mapping: Dict[str, List[str]]) -> Optional[str]:
        for normalized_value, keywords in mapping.items():
            for keyword in keywords:
                if keyword in text:
                    return normalized_value
        return None

    def _extract_multi_keywords(self, text: str, mapping: Dict[str, List[str]]) -> List[str]:
        matched: List[str] = []
        for normalized_value, keywords in mapping.items():
            if any(keyword in text for keyword in keywords):
                matched.append(normalized_value)
        return matched

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", "", (text or "").lower())

    @staticmethod
    def _ctx_get(scene_context: Optional[Any], key: str) -> Optional[Any]:
        if scene_context is None:
            return None
        if isinstance(scene_context, dict):
            return scene_context.get(key)
        return getattr(scene_context, key, None)

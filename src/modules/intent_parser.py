from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class IntentParseResult:
    intent: str
    confidence: float
    slots: Dict[str, Any] = field(default_factory=dict)
    need_clarify: bool = False
    reason: str = ""


class IntentParser:
    PAGE_ALIASES = {
        "地图": "map",
        "地图页": "map",
        "地图页面": "map",
        "推荐": "recommend",
        "推荐页": "recommend",
        "推荐页面": "recommend",
        "路线": "route",
        "路线页": "route",
        "路线页面": "route",
        "首页": "home",
        "主页": "home",
        "主页面": "home",
        "详情页": "scenic_detail",
        "景点详情": "scenic_detail",
        "门票页": "ticket",
        "门票页面": "ticket",
        "个人中心": "profile",
        "我的页面": "profile",
        "当前页": "current",
        "这个页面": "current",
        "当前页面": "current",
    }

    def parse(self, query: str) -> IntentParseResult:
        text = (query or "").strip()
        if not text:
            return IntentParseResult(
                intent="unknown",
                confidence=0.0,
                need_clarify=True,
                reason="空输入",
            )

        # 1. 问候 / 感谢
        if any(x in text for x in ["你好", "您好", "嗨", "hello", "hi", "导游你好"]):
            return IntentParseResult(
                intent="greeting",
                confidence=0.98,
                reason="识别到问候语",
            )

        if any(x in text for x in ["谢谢", "感谢", "辛苦了", "多谢"]):
            return IntentParseResult(
                intent="thanks",
                confidence=0.98,
                reason="识别到感谢语",
            )

        # 2. 数字人显示/隐藏
        if any(x in text for x in ["显示数字人", "叫出导游", "叫出数字人", "让讲解员出来", "显示导游"]):
            return IntentParseResult(
                intent="ui_show_avatar",
                confidence=0.96,
                slots={
                    "ui_action": "show_avatar",
                    "trigger_source": "user_voice",
                },
                reason="识别到数字人显示意图",
            )

        if any(x in text for x in ["隐藏数字人", "关闭数字人", "隐藏导游", "先别讲了", "闭嘴", "暂停讲解"]):
            return IntentParseResult(
                intent="ui_hide_avatar",
                confidence=0.95,
                slots={
                    "ui_action": "hide_avatar",
                    "trigger_source": "user_voice",
                },
                reason="识别到数字人隐藏意图",
            )

        # 3. 页面介绍
        if any(x in text for x in ["这个页面是干嘛的", "这个页面怎么用", "介绍一下这个页面", "讲讲这个页面"]):
            return IntentParseResult(
                intent="ui_page_intro",
                confidence=0.94,
                slots={
                    "target_page": "current",
                    "ui_action": "intro",
                    "trigger_source": "user_voice",
                },
                reason="识别到当前页面介绍意图",
            )

        for alias, page_id in self.PAGE_ALIASES.items():
            if alias in text and any(x in text for x in ["介绍", "怎么用", "是干嘛", "讲讲"]):
                return IntentParseResult(
                    intent="ui_page_intro",
                    confidence=0.94,
                    slots={
                        "target_page": page_id,
                        "ui_action": "intro",
                        "trigger_source": "user_voice",
                    },
                    reason="识别到指定页面介绍意图",
                )

        # 4. 页面关闭
        if any(x in text for x in ["关闭这个页面", "关闭当前页", "退出当前页", "关掉这个页面", "关闭当前页面"]):
            return IntentParseResult(
                intent="ui_close_page",
                confidence=0.95,
                slots={
                    "target_page": "current",
                    "ui_action": "close",
                    "trigger_source": "user_voice",
                },
                reason="识别到关闭当前页意图",
            )

        for alias, page_id in self.PAGE_ALIASES.items():
            if alias in text and any(x in text for x in ["关闭", "退出", "关掉"]):
                return IntentParseResult(
                    intent="ui_close_page",
                    confidence=0.95,
                    slots={
                        "target_page": page_id,
                        "ui_action": "close",
                        "trigger_source": "user_voice",
                    },
                    reason="识别到关闭指定页面意图",
                )

        # 5. 页面跳转
        for alias, page_id in self.PAGE_ALIASES.items():
            if alias in text and any(x in text for x in ["打开", "去", "跳到", "切到", "进入", "带我去", "前往"]):
                return IntentParseResult(
                    intent="ui_navigate_page",
                    confidence=0.96,
                    slots={
                        "target_page": page_id,
                        "ui_action": "navigate",
                        "trigger_source": "user_voice",
                    },
                    reason="识别到页面跳转意图",
                )

        # 6. 景点全量列举
        if any(x in text for x in ["有什么景点", "有哪些景点", "景点有哪些", "全部景点", "所有景点", "核心景点"]):
            return IntentParseResult(
                intent="spot_list",
                confidence=0.97,
                reason="识别到景点列举意图",
            )

        # 7. 景点推荐
        if any(x in text for x in ["推荐景点", "必打卡", "最值得看", "第一次去看什么", "推荐哪些景点"]):
            return IntentParseResult(
                intent="spot_recommend",
                confidence=0.93,
                reason="识别到景点推荐意图",
            )

        # 8. 路线规划
        if any(x in text for x in ["路线", "怎么逛", "怎么玩", "半天", "一天", "亲子路线", "游玩路线"]):
            return IntentParseResult(
                intent="route_plan",
                confidence=0.92,
                reason="识别到路线规划意图",
            )

        # 9. 导航路径
        if any(x in text for x in ["怎么走", "从"]) and any(x in text for x in ["到", "去"]):
            return IntentParseResult(
                intent="navigation_route",
                confidence=0.92,
                reason="识别到导航路径意图",
            )

        # 10. 景点讲解
        if any(x in text for x in ["是什么", "什么意思", "讲的是什么", "介绍一下"]) and any(
            x in text for x in ["九龙灌浴", "灵山大佛", "梵宫", "拈花广场", "五灯湖"]
        ):
            return IntentParseResult(
                intent="spot_explain",
                confidence=0.90,
                reason="识别到景点讲解意图",
            )

        return IntentParseResult(
            intent="unknown",
            confidence=0.3,
            need_clarify=False,
            reason="未命中显式规则，默认 unknown",
        )

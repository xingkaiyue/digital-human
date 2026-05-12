import json
from typing import List
from urllib import error, request

from .base import ChatMessage, LLMResponse


class OpenAICompatibleClient:
    def __init__(
        self,
        provider: str,
        model: str,
        api_key: str,
        base_url: str,
        timeout_seconds: int = 60,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_tokens = max_tokens

    @property
    def chat_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def chat(self, messages: List[ChatMessage]) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=self.chat_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"{self.provider} 接口调用失败: HTTP {exc.code} {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"{self.provider} 接口连接失败: {exc.reason}") from exc

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"{self.provider} 返回结果中没有 choices: {data}")

        message = choices[0].get("message") or {}
        content = message.get("content", "")
        finish_reason = choices[0].get("finish_reason")

        return LLMResponse(content=content, model=self.model, finish_reason=finish_reason)

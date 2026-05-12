from config import AppSettings

from .openai_compatible import OpenAICompatibleClient


def build_llm_client(settings: AppSettings) -> OpenAICompatibleClient:
    if not settings.llm_api_key:
        raise ValueError(
            "未配置 LLM API Key。请设置 RAG_LLM_API_KEY，或为对应 provider 设置 DEEPSEEK_API_KEY / ZHIPU_API_KEY。"
        )

    return OpenAICompatibleClient(
        provider=settings.llm_provider,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )

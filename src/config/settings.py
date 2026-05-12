import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = BASE_DIR / "src" / "data"
DEFAULT_MODEL_DIR = BASE_DIR / "all-MiniLM-L6-v2"
DEFAULT_CHROMA_DIR = BASE_DIR / "chroma_db"
DEFAULT_ENV_FILE = BASE_DIR / ".env"


def _load_dotenv_file() -> None:
    if not DEFAULT_ENV_FILE.exists():
        return

    for raw_line in DEFAULT_ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env(key: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(key)
    if value is None or value == "":
        return default
    return value


@dataclass(frozen=True)
class AppSettings:
    project_root: Path
    data_dir: Path
    embedding_model_path: Path
    chroma_dir: Path
    guide_collection: str
    structured_collection: str
    chunk_size: int
    chunk_overlap: int
    embedding_batch_size: int
    retrieval_top_k: int
    retrieval_recall_k: int
    llm_provider: str
    llm_model: str
    llm_api_key: Optional[str]
    llm_base_url: str
    llm_timeout_seconds: int
    llm_temperature: float
    llm_max_tokens: int

    xfyun_asr_app_id: Optional[str]
    xfyun_asr_api_key: Optional[str]
    xfyun_asr_api_secret: Optional[str]

    xfyun_tts_app_id: str
    xfyun_tts_api_key: str
    xfyun_tts_api_secret: str

    tencent_map_key: Optional[str]
    tencent_map_sk: Optional[str]
    tencent_map_region: str

    serpapi_api_key: Optional[str]
    serpapi_base_url: str
    serpapi_timeout_seconds: int
    serpapi_default_num: int
    serpapi_hl: str
    serpapi_gl: str


    @property
    def has_serpapi_credentials(self) -> bool:
        return bool(self.serpapi_api_key)


    @property
    def has_llm_credentials(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def has_xfyun_asr_credentials(self) -> bool:
        return bool(
            self.xfyun_asr_app_id and self.xfyun_asr_api_key and self.xfyun_asr_api_secret
        )

    @property
    def has_tencent_map_credentials(self) -> bool:
        return bool(self.tencent_map_key and self.tencent_map_sk)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    _load_dotenv_file()
    provider = (_env("RAG_LLM_PROVIDER", "deepseek") or "deepseek").lower()

    default_model = {
        "deepseek": "deepseek-chat",
        "zhipu": "glm-4.5",
    }.get(provider, "deepseek-chat")

    default_base_url = {
        "deepseek": "https://api.deepseek.com",
        "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    }.get(provider, "https://api.deepseek.com")

    api_key = _env("RAG_LLM_API_KEY")
    if not api_key:
        api_key = _env("DEEPSEEK_API_KEY") if provider == "deepseek" else _env("ZHIPU_API_KEY")

    return AppSettings(
        project_root=BASE_DIR,
        data_dir=Path(_env("RAG_DATA_DIR", str(DEFAULT_DATA_DIR))).resolve(),
        embedding_model_path=Path(
            _env("RAG_EMBEDDING_MODEL_PATH", str(DEFAULT_MODEL_DIR))
        ).resolve(),
        chroma_dir=Path(_env("RAG_CHROMA_DIR", str(DEFAULT_CHROMA_DIR))).resolve(),
        guide_collection=_env("RAG_GUIDE_COLLECTION", "rag_guide") or "rag_guide",
        structured_collection=_env("RAG_STRUCTURED_COLLECTION", "rag_structured") or "rag_structured",
        chunk_size=int(_env("RAG_CHUNK_SIZE", "500") or "500"),
        chunk_overlap=int(_env("RAG_CHUNK_OVERLAP", "80") or "80"),
        embedding_batch_size=int(_env("RAG_EMBEDDING_BATCH_SIZE", "32") or "32"),
        retrieval_top_k=int(_env("RAG_RETRIEVAL_TOP_K", "4") or "4"),
        retrieval_recall_k=int(_env("RAG_RETRIEVAL_RECALL_K", "10") or "10"),
        llm_provider=provider,
        llm_model=_env("RAG_LLM_MODEL", default_model) or default_model,
        llm_api_key=api_key,
        llm_base_url=_env("RAG_LLM_BASE_URL", default_base_url) or default_base_url,
        llm_timeout_seconds=int(_env("RAG_LLM_TIMEOUT_SECONDS", "60") or "60"),
        llm_temperature=float(_env("RAG_LLM_TEMPERATURE", "0.2") or "0.2"),
        llm_max_tokens=int(_env("RAG_LLM_MAX_TOKENS", "1024") or "1024"),
        xfyun_asr_app_id=_env("XFYUN_ASR_APP_ID"),
        xfyun_asr_api_key=_env("XFYUN_ASR_API_KEY"),
        xfyun_asr_api_secret=_env("XFYUN_ASR_API_SECRET"),
        xfyun_tts_app_id=os.getenv("XFYUN_TTS_APP_ID", ""),
        xfyun_tts_api_key=os.getenv("XFYUN_TTS_API_KEY", ""),
        xfyun_tts_api_secret=os.getenv("XFYUN_TTS_API_SECRET", ""),
        tencent_map_key=_env("TENCENT_MAP_KEY"),
        tencent_map_sk=_env("TENCENT_MAP_SK"),
        tencent_map_region=_env("TENCENT_MAP_REGION", "CN") or "CN",
        serpapi_api_key=_env("SERPAPI_API_KEY"),
        serpapi_base_url=_env("SERPAPI_BASE_URL",
                              "https://serpapi.com/search.json") or "https://serpapi.com/search.json",
        serpapi_timeout_seconds=int(_env("SERPAPI_TIMEOUT_SECONDS", "15") or "15"),
        serpapi_default_num=int(_env("SERPAPI_DEFAULT_NUM", "10") or "10"),
        serpapi_hl=_env("SERPAPI_HL", "zh-cn") or "zh-cn",
        serpapi_gl=_env("SERPAPI_GL", "cn") or "cn",
    )

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from config import AppSettings
from utils.xfyun_asr_ws import XFYunRealtimeASR


class XFYunASRService:
    """
    讯飞 ASR 服务封装。
    当前版本直接适配 utils.xfyun_asr_ws.XFYunRealtimeASR
    只支持 wav 文件，推荐 16k / 16bit / 单声道 PCM wav
    """

    def __init__(self, settings: AppSettings):
        self.appid = settings.xfyun_asr_app_id
        self.api_key = settings.xfyun_asr_api_key
        self.api_secret = settings.xfyun_asr_api_secret

        if not self.appid or not self.api_key or not self.api_secret:
            raise RuntimeError(
                "讯飞 ASR 配置缺失，请检查 .env / config 中的 "
                "xfyun_asr_app_id / xfyun_asr_api_key / xfyun_asr_api_secret"
            )

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        suffix: str = ".wav",
        content_type: Optional[str] = None,
    ) -> str:
        suffix = (suffix or ".wav").lower()

        if suffix != ".wav":
            raise ValueError("当前 ASR 仅支持 wav 文件，请先转成 16k PCM wav 后再上传。")

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            temp_path = Path(tmp.name)

        try:
            client = XFYunRealtimeASR(
                appid=self.appid,
                api_key=self.api_key,
                api_secret=self.api_secret,
            )
            text = client.transcribe(str(temp_path))
            return (text or "").strip()
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass

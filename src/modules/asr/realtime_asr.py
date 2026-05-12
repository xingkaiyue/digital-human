from config import get_settings
from tools.audio_utils import check_wav_format
from utils.xfyun_asr_ws import XFYunRealtimeASR


class RealtimeASRModel:
    def __init__(self):
        settings = get_settings()
        if not settings.has_xfyun_asr_credentials:
            raise ValueError("未配置讯飞 ASR 凭据，请设置 XFYUN_ASR_APP_ID / XFYUN_ASR_API_KEY / XFYUN_ASR_API_SECRET")

        self.asr_client = XFYunRealtimeASR(
            appid=settings.xfyun_asr_app_id,
            api_key=settings.xfyun_asr_api_key,
            api_secret=settings.xfyun_asr_api_secret,
        )

    def transcribe(self, wav_path: str) -> str:
        check_wav_format(wav_path)
        return self.asr_client.transcribe(wav_path).strip()


_asr_model = None


def realtime_asr(wav_path: str) -> str:
    global _asr_model
    if _asr_model is None:
        _asr_model = RealtimeASRModel()
    return _asr_model.transcribe(wav_path)

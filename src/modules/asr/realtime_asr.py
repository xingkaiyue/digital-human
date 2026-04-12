# src/modules/asr/realtime_asr.py
from src.utils.xfyun_asr_ws import XFYunRealtimeASR
from src.config.settings import (
    XFYUN_ASR_APP_ID,
    XFYUN_ASR_API_KEY,
    XFYUN_ASR_API_SECRET
)
from src.tools.audio_utils import check_wav_format


class RealtimeASRModel:

    def __init__(self):
        self.asr_client = XFYunRealtimeASR(
            appid=XFYUN_ASR_APP_ID,
            api_key=XFYUN_ASR_API_KEY,
            api_secret=XFYUN_ASR_API_SECRET
        )

    def transcribe(self, wav_path: str) -> str:
        check_wav_format(wav_path)
        return self.asr_client.transcribe(wav_path).strip()


# ======== 给外部用的快捷方法（函数式） ========
_asr_model = None


def realtime_asr(wav_path: str) -> str:
    """
    快捷调用方式：
    text = realtime_asr("test.wav")
    """
    global _asr_model
    if _asr_model is None:
        _asr_model = RealtimeASRModel()
    return _asr_model.transcribe(wav_path)
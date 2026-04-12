# src/tools/audio_utils.py
import wave


def check_wav_format(wav_path: str):
    """
    校验 wav 是否符合讯飞 ASR 要求
    """
    with wave.open(wav_path, "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        framerate = wf.getframerate()

    if channels != 1:
        raise ValueError("音频必须是单声道")

    if sample_width != 2:
        raise ValueError("采样位宽必须是 16bit")

    if framerate not in (16000, 8000):
        raise ValueError("采样率必须是 8k 或 16k")

    return True
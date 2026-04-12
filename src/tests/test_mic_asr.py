# src/tests/test_mic_asr.py

from src.modules.asr.xfyun_mic_stream_asr import XFYunMicStreamASR


def on_partial(text):
    print("🟡 中间：", text)


def on_final(text):
    print("🟢 最终：", text)


if __name__ == "__main__":
    asr = XFYunMicStreamASR(
        on_partial=on_partial,
        on_final=on_final
    )
    asr.start()
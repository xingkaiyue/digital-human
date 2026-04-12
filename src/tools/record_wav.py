# src/tools/record_wav.py
import sounddevice as sd
from scipy.io.wavfile import write
import os

SAMPLE_RATE = 16000   # 讯飞推荐 16k
CHANNELS = 1          # 单声道
DURATION = 5          # 录音 5 秒

def record_wav(save_path="test.wav"):
    print("🎙️ 开始录音，请说话...")
    audio = sd.rec(
        int(DURATION * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16"
    )
    sd.wait()
    write(save_path, SAMPLE_RATE, audio)
    print(f"✅ 录音完成，已保存为 {os.path.abspath(save_path)}")

if __name__ == "__main__":
    record_wav()
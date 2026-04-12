# src/tests/test_asr.py
import os
from src.modules.asr.realtime_asr import realtime_asr

# 当前文件所在目录
BASE_DIR = os.path.dirname(__file__)

# 绝对路径指向 test.wav
wav_path = os.path.join(BASE_DIR, "test.wav")

print("🎤 开始语音识别...")
text = realtime_asr(wav_path)
print("识别结果：", text)
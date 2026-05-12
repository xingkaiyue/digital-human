import base64
import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8001"

GUIDE_ANSWER_PAYLOAD = {
    "query": "拈花湾禅意小镇有什么好玩的地方吗？",
    "destination_id": None,
    "destination_name": "拈花湾禅意小镇",
    "scenic_id": None,
    "scenic_name": None,
    "scope_mode": "current_only",
    "style": "guide",
    "audience": "general",
    "max_length": 1000,
    "include_tips": True,
    "include_next_suggestion": True,
}


TTS_VOICE = "xiaolu"


def play_file(path: str) -> None:
    system_name = platform.system()
    if system_name == "Windows":
        os.startfile(path)
    elif system_name == "Darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


def save_audio_file(audio_base64: str, suffix: str = ".mp3") -> Path:
    output_dir = Path("tmp_tts_outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"guide_answer_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{suffix}"
    audio_bytes = base64.b64decode(audio_base64)

    with open(output_file, "wb") as f:
        f.write(audio_bytes)

    return output_file


def main() -> None:
    guide_resp = requests.post(
        f"{BASE_URL}/api/v1/guide/guide-answer",
        json=GUIDE_ANSWER_PAYLOAD,
        timeout=60,
    )
    guide_resp.raise_for_status()
    guide_data = guide_resp.json()

    knowledge_answer = guide_data.get("knowledge_answer", "")
    guide_answer = guide_data.get("guide_answer", "")

    print("知识库原始回答：")
    print(knowledge_answer)
    print("\n" + "=" * 80 + "\n")
    print("导游式回答：")
    print(guide_answer)

    if not guide_answer.strip():
        raise ValueError("guide-answer 接口返回的 guide_answer 为空")

    tts_resp = requests.post(
        f"{BASE_URL}/api/v1/guide/tts",
        json={
            "text": guide_answer,
            "voice": TTS_VOICE,
            "speed": 50,
            "volume": 50,
            "pitch": 50,
            "audio_format": "mp3",
        },
        timeout=60,
    )
    tts_resp.raise_for_status()
    tts_data = tts_resp.json()

    audio_base64 = tts_data.get("audio_base64")
    if not audio_base64:
        raise ValueError("TTS 接口未返回 audio_base64")

    output_file = save_audio_file(audio_base64, suffix=".mp3")

    print(f"\n已生成语音文件: {output_file.resolve()}")
    play_file(str(output_file.resolve()))


if __name__ == "__main__":
    main()

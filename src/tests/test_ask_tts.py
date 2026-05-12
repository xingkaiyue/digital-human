import base64
import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8001"

ASK_PAYLOAD = {
    "query": "灵山大佛的文化内涵是什么？",
    "destination_id": None,
    "destination_name": "灵山景区",
    "scenic_id": None,
    "scenic_name": None,
    "scope_mode": "current_only",
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

    output_file = output_dir / f"ask_answer_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{suffix}"
    audio_bytes = base64.b64decode(audio_base64)

    with open(output_file, "wb") as f:
        f.write(audio_bytes)

    return output_file


def main() -> None:
    ask_resp = requests.post(
        f"{BASE_URL}/api/v1/guide/ask",
        json=ASK_PAYLOAD,
        timeout=60,
    )
    ask_resp.raise_for_status()
    ask_data = ask_resp.json()

    answer = ask_data["answer"]
    print("知识库回答：")
    print(answer)

    tts_resp = requests.post(
        f"{BASE_URL}/api/v1/guide/tts",
        json={
            "text": answer,
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

    print(f"已生成语音文件: {output_file.resolve()}")
    play_file(str(output_file.resolve()))


if __name__ == "__main__":
    main()

import base64
import os
import platform
import subprocess

import requests

BASE_URL = "http://127.0.0.1:8001"

UI_EVENT_PAYLOAD = {
    "event_type": "page_enter",
    "page_id": "scenic_detail",
    "destination_id": None,
    "destination_name": "灵山景区",
    "scenic_id": None,
    "scenic_name": "灵山大佛",
    "scope_mode": "current_only",
    "user_profile": {},
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


def main() -> None:
    ui_resp = requests.post(
        f"{BASE_URL}/api/v1/guide/ui-event",
        json=UI_EVENT_PAYLOAD,
        timeout=60,
    )
    ui_resp.raise_for_status()
    ui_data = ui_resp.json()

    speech_text = ui_data.get("speech_text") or "欢迎进入页面。"
    print("页面播报文案：")
    print(speech_text)

    tts_resp = requests.post(
        f"{BASE_URL}/api/v1/guide/tts",
        json={
            "text": speech_text,
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

    output_file = "ui_event_speech.mp3"
    with open(output_file, "wb") as f:
        f.write(base64.b64decode(tts_data["audio_base64"]))

    print(f"已生成语音文件: {output_file}")
    play_file(output_file)


if __name__ == "__main__":
    main()

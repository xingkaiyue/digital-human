import base64
import json
import threading
from queue import Queue
from typing import Callable, Optional

import websocket

from config import get_settings
from utils.xfyun_auth import create_ws_url


class XFYunStreamASR:
    def __init__(
        self,
        on_partial: Optional[Callable[[str], None]] = None,
        on_final: Optional[Callable[[str], None]] = None,
    ):
        settings = get_settings()
        if not settings.has_xfyun_asr_credentials:
            raise ValueError("未配置讯飞 ASR 凭据，请设置 XFYUN_ASR_APP_ID / XFYUN_ASR_API_KEY / XFYUN_ASR_API_SECRET")

        self.app_id = settings.xfyun_asr_app_id
        self.api_key = settings.xfyun_asr_api_key
        self.api_secret = settings.xfyun_asr_api_secret
        self.on_partial = on_partial
        self.on_final = on_final
        self.audio_queue: Queue[bytes | None] = Queue()
        self.ws = None
        self.running = False

    def start(self) -> None:
        ws_url = create_ws_url(self.api_key, self.api_secret)
        self.ws = websocket.WebSocketApp(
            ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.running = True
        threading.Thread(target=self.ws.run_forever, daemon=True).start()

    def send_pcm(self, pcm_bytes: bytes) -> None:
        if not isinstance(pcm_bytes, (bytes, bytearray)):
            raise TypeError("pcm_bytes must be bytes")
        if self.running and pcm_bytes:
            self.audio_queue.put(bytes(pcm_bytes))

    def send_base64(self, b64_audio: str) -> None:
        self.send_pcm(base64.b64decode(b64_audio))

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        self.audio_queue.put(None)
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def _on_open(self, ws) -> None:
        first_frame = {
            "common": {"app_id": self.app_id},
            "business": {
                "language": "zh_cn",
                "domain": "iat",
                "accent": "mandarin",
                "vad_eos": 2000,
            },
            "data": {
                "status": 0,
                "format": "audio/L16;rate=16000",
                "encoding": "raw",
                "audio": "",
            },
        }
        ws.send(json.dumps(first_frame))
        threading.Thread(target=self._audio_send_loop, daemon=True).start()

    def _audio_send_loop(self) -> None:
        while True:
            audio = self.audio_queue.get()
            if audio is None:
                break
            frame = {
                "data": {
                    "status": 1,
                    "format": "audio/L16;rate=16000",
                    "encoding": "raw",
                    "audio": base64.b64encode(audio).decode("utf-8"),
                }
            }
            try:
                if self.ws:
                    self.ws.send(json.dumps(frame))
            except Exception:
                break

        end_frame = {
            "data": {
                "status": 2,
                "format": "audio/L16;rate=16000",
                "encoding": "raw",
                "audio": "",
            }
        }
        try:
            if self.ws:
                self.ws.send(json.dumps(end_frame))
        except Exception:
            pass

    def _on_message(self, ws, message) -> None:
        msg = json.loads(message)
        if msg.get("code", 0) != 0:
            return

        result = ((msg.get("data") or {}).get("result")) or {}
        ws_items = result.get("ws") or []
        text = "".join(word["w"] for item in ws_items for word in item.get("cw", []))
        if not text:
            return

        if result.get("ls"):
            if self.on_final:
                self.on_final(text)
        elif self.on_partial:
            self.on_partial(text)

    @staticmethod
    def _on_error(ws, error) -> None:
        print(f"ASR WebSocket error: {error}")

    @staticmethod
    def _on_close(ws, *args) -> None:
        print("ASR WebSocket closed")


XFYunMicStreamASR = XFYunStreamASR

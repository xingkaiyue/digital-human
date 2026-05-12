import base64
import json
import threading
import time
import wave

import websocket

from utils.xfyun_auth import create_ws_url


class XFYunRealtimeASR:
    def __init__(self, appid: str, api_key: str, api_secret: str):
        self.appid = appid
        self.api_key = api_key
        self.api_secret = api_secret
        self.ws_url = create_ws_url(api_key=self.api_key, api_secret=self.api_secret)
        self.ws = None
        self.wav_path = None
        self.result_text = ""
        self._closed = False

    def transcribe(self, wav_path: str) -> str:
        self.wav_path = wav_path
        self.result_text = ""
        self._closed = False

        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.ws.run_forever(ping_interval=30, ping_timeout=10)
        return self.result_text

    def _on_open(self, ws) -> None:
        first_frame = {
            "common": {"app_id": self.appid},
            "business": {
                "language": "zh_cn",
                "domain": "iat",
                "accent": "mandarin",
                "vad_eos": 3000,
            },
            "data": {
                "status": 0,
                "format": "audio/L16;rate=16000",
                "encoding": "raw",
                "audio": "",
            },
        }
        ws.send(json.dumps(first_frame))
        threading.Thread(target=self._send_audio, args=(ws,), daemon=True).start()

    def _send_audio(self, ws) -> None:
        try:
            with wave.open(self.wav_path, "rb") as wf:
                while True:
                    buf = wf.readframes(1280)
                    if not buf:
                        break

                    audio_frame = {
                        "data": {
                            "status": 1,
                            "format": "audio/L16;rate=16000",
                            "encoding": "raw",
                            "audio": base64.b64encode(buf).decode("utf-8"),
                        }
                    }
                    if ws.sock and ws.sock.connected:
                        ws.send(json.dumps(audio_frame))
                    time.sleep(0.04)

            end_frame = {
                "data": {
                    "status": 2,
                    "format": "audio/L16;rate=16000",
                    "encoding": "raw",
                    "audio": "",
                }
            }
            if ws.sock and ws.sock.connected:
                ws.send(json.dumps(end_frame))
        except Exception as exc:
            print(f"ASR audio send failed: {exc}")

    def _on_message(self, ws, message) -> None:
        msg = json.loads(message)
        if msg.get("code", 0) != 0:
            self._safe_close(ws)
            return

        data = msg.get("data") or {}
        result = data.get("result") or {}
        ws_list = result.get("ws") or []
        for ws_item in ws_list:
            for cw in ws_item.get("cw", []):
                self.result_text += cw.get("w", "")

        if data.get("status") == 2:
            self._safe_close(ws)

    @staticmethod
    def _on_error(ws, error) -> None:
        print(f"ASR WebSocket error: {error}")

    @staticmethod
    def _on_close(ws, close_status_code, close_msg) -> None:
        print("ASR WebSocket closed")

    def _safe_close(self, ws) -> None:
        if not self._closed:
            self._closed = True
            if ws.sock and ws.sock.connected:
                ws.close()

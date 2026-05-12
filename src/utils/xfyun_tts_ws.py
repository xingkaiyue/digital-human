from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import ssl
from email.utils import formatdate
from urllib.parse import urlencode

from dotenv import load_dotenv
import websocket


load_dotenv()


class XFYunRealtimeTTS:
    """
    讯飞 WebSocket TTS
    返回完整音频 bytes，默认 pcm/raw

    关键策略：
    1. 不再猜测展示名对应的 vcn
    2. 通过环境变量显式配置真实 vcn
    3. 未知音色直接报错，避免静默回退默认音色
    """

    def __init__(
        self,
        appid: str,
        api_key: str,
        api_secret: str,
        host: str = "tts-api.xfyun.cn",
        request_path: str = "/v2/tts",
    ):
        if not appid:
            raise ValueError("XFYUN_TTS_APP_ID is required")
        if not api_key:
            raise ValueError("XFYUN_TTS_API_KEY is required")
        if not api_secret:
            raise ValueError("XFYUN_TTS_API_SECRET is required")

        self.appid = appid
        self.api_key = api_key
        self.api_secret = api_secret
        self.host = host
        self.request_path = request_path


        self.voice_map = {
            "xiaolu": os.getenv("XFYUN_TTS_VCN_XIAOLU", "xiaolu").strip(),
            "小露": os.getenv("XFYUN_TTS_VCN_XIAOLU", "xiaolu").strip(),
            "lingfeizhe": os.getenv("XFYUN_TTS_VCN_LINGFEIZHE", "lingfeizhe").strip(),
            "聆飞哲": os.getenv("XFYUN_TTS_VCN_LINGFEIZHE", "lingfeizhe").strip(),
            "xiaoyan": "xiaoyan",
            "小燕": "xiaoyan",
        }

    def synthesize_bytes(
        self,
        text: str,
        voice: str = "xiaoyan",
        speed: int = 50,
        volume: int = 50,
        pitch: int = 50,
        aue: str = "raw",
        auf: str = "audio/L16;rate=16000",
    ) -> bytes:
        text = (text or "").strip()
        if not text:
            raise ValueError("text must not be empty")

        final_voice = self._normalize_voice(voice)
        final_speed = self._clamp(speed, 0, 100)
        final_volume = self._clamp(volume, 0, 100)
        final_pitch = self._clamp(pitch, 0, 100)

        print(
            "XFYunRealtimeTTS request ->",
            {
                "voice_input": voice,
                "voice_final_vcn": final_voice,
                "speed": final_speed,
                "volume": final_volume,
                "pitch": final_pitch,
                "aue": aue,
                "auf": auf,
                "text_preview": text[:80],
            },
        )

        ws_url = self._build_auth_url()
        audio_chunks: list[bytes] = []
        error_holder = {"error": None}
        finished = {"done": False}

        def on_message(ws, message):
            try:
                payload = json.loads(message)
            except Exception as exc:
                error_holder["error"] = RuntimeError(f"TTS response decode failed: {exc}")
                ws.close()
                return

            code = payload.get("code", -1)
            sid = payload.get("sid")
            if code != 0:
                err_msg = payload.get("message") or "unknown tts error"
                error_holder["error"] = RuntimeError(
                    f"XFYun TTS error code={code}, sid={sid}, message={err_msg}, vcn={final_voice}"
                )
                ws.close()
                return

            data = payload.get("data", {}) or {}
            audio_b64 = data.get("audio")
            status = data.get("status")

            if audio_b64:
                try:
                    audio_chunks.append(base64.b64decode(audio_b64))
                except Exception as exc:
                    error_holder["error"] = RuntimeError(f"audio decode failed: {exc}")
                    ws.close()
                    return

            if status == 2:
                finished["done"] = True
                ws.close()

        def on_error(ws, error):
            if not error_holder["error"]:
                error_holder["error"] = RuntimeError(f"TTS websocket error: {error}")

        def on_close(ws, close_status_code, close_msg):
            if not finished["done"] and not error_holder["error"]:
                error_holder["error"] = RuntimeError(
                    f"TTS websocket closed unexpectedly: "
                    f"code={close_status_code}, msg={close_msg}, vcn={final_voice}"
                )

        def on_open(ws):
            payload = {
                "common": {
                    "app_id": self.appid,
                },
                "business": {
                    "aue": aue,
                    "auf": auf,
                    "vcn": final_voice,
                    "tte": "utf8",
                    "speed": final_speed,
                    "volume": final_volume,
                    "pitch": final_pitch,
                },
                "data": {
                    "status": 2,
                    "text": base64.b64encode(text.encode("utf-8")).decode("utf-8"),
                },
            }

            print("XFYunRealtimeTTS payload.business ->", payload["business"])
            ws.send(json.dumps(payload, ensure_ascii=False))

        ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )

        ws.run_forever(
            sslopt={"cert_reqs": ssl.CERT_NONE},
            ping_interval=20,
            ping_timeout=10,
        )

        if error_holder["error"]:
            raise error_holder["error"]

        audio = b"".join(audio_chunks)
        if not audio:
            raise RuntimeError(f"No audio data returned from XFYun TTS, vcn={final_voice}")

        return audio

    def _normalize_voice(self, voice: str) -> str:
        v = (voice or "").strip()
        if not v:
            raise ValueError("voice must not be empty")

        if v not in self.voice_map:
            raise ValueError(
                f"Unsupported voice: {v}. Supported voices: {sorted(set(self.voice_map.keys()))}"
            )

        final_vcn = self.voice_map[v]
        if not final_vcn:
            raise ValueError(f"Voice mapping for {v} is empty")

        return final_vcn

    def _build_auth_url(self) -> str:
        date = formatdate(timeval=None, localtime=False, usegmt=True)

        signature_origin = (
            f"host: {self.host}\n"
            f"date: {date}\n"
            f"GET {self.request_path} HTTP/1.1"
        )

        signature_sha = hmac.new(
            self.api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()

        signature = base64.b64encode(signature_sha).decode("utf-8")

        authorization_origin = (
            f'api_key="{self.api_key}", '
            f'algorithm="hmac-sha256", '
            f'headers="host date request-line", '
            f'signature="{signature}"'
        )

        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")

        query = {
            "authorization": authorization,
            "date": date,
            "host": self.host,
        }

        return f"wss://{self.host}{self.request_path}?{urlencode(query)}"

    @staticmethod
    def _clamp(value: int, min_value: int, max_value: int) -> int:
        return max(min_value, min(max_value, int(value)))

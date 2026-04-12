import websocket
import json
import time
import threading
import base64
import wave

from src.config.settings import (
    XFYUN_ASR_APP_ID,
    XFYUN_ASR_API_KEY,
    XFYUN_ASR_API_SECRET
)
from src.utils.xfyun_auth import create_ws_url


class XFYunRealtimeASR:
    """
    讯飞实时语音转写（WebSocket）
    - wav: 16kHz / 16bit / mono
    """

    def __init__(self, appid: str = None, api_key: str = None, api_secret: str = None):
        # 优先使用传入参数，其次使用 settings
        self.appid = appid or XFYUN_ASR_APP_ID
        self.api_key = api_key or XFYUN_ASR_API_KEY
        self.api_secret = api_secret or XFYUN_ASR_API_SECRET

        self.ws_url = create_ws_url(
            api_key=self.api_key,
            api_secret=self.api_secret
        )

        self.ws = None
        self.wav_path = None
        self.result_text = ""
        self._closed = False

    # ================= WebSocket 回调 =================

    def _on_open(self, ws):
        print("🔗 WebSocket 已连接")

        # 1️⃣ 首帧（只能发一次）
        first_frame = {
            "common": {
                "app_id": self.appid
            },
            "business": {
                "language": "zh_cn",
                "domain": "iat",
                "accent": "mandarin",
                "vad_eos": 3000
            },
            "data": {
                "status": 0,
                "format": "audio/L16;rate=16000",
                "encoding": "raw",
                "audio": ""
            }
        }

        ws.send(json.dumps(first_frame))

        # 2️⃣ 后台线程发送音频
        threading.Thread(
            target=self._send_audio,
            args=(ws,),
            daemon=True
        ).start()

    def _send_audio(self, ws):
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
                            "audio": base64.b64encode(buf).decode("utf-8")
                        }
                    }

                    if ws.sock and ws.sock.connected:
                        ws.send(json.dumps(audio_frame))

                    time.sleep(0.04)

            # 3️⃣ 结束帧（必须）
            end_frame = {
                "data": {
                    "status": 2,
                    "format": "audio/L16;rate=16000",
                    "encoding": "raw",
                    "audio": ""
                }
            }

            if ws.sock and ws.sock.connected:
                ws.send(json.dumps(end_frame))

        except Exception as e:
            print("❌ 音频发送异常:", e)

    def _on_message(self, ws, message):
        msg = json.loads(message)

        # 错误帧
        if msg.get("code", 0) != 0:
            print("❌ ASR Error:", msg)
            self._safe_close(ws)
            return

        data = msg.get("data")
        if not data:
            return

        # 识别结果
        if "result" in data:
            ws_list = data["result"]["ws"]
            for ws_item in ws_list:
                for cw in ws_item["cw"]:
                    self.result_text += cw["w"]

        # ⭐ 识别结束，主动关闭（解决 timeout 的关键）
        if data.get("status") == 2:
            self._safe_close(ws)

    def _on_error(self, ws, error):
        print("❌ WebSocket Error:", error)

    def _on_close(self, ws, close_status_code, close_msg):
        print("🔒 WebSocket 已关闭")

    # ================= 工具方法 =================

    def _safe_close(self, ws):
        if not self._closed:
            self._closed = True
            if ws.sock and ws.sock.connected:
                ws.close()

    # ================= 对外接口 =================

    def transcribe(self, wav_path: str) -> str:
        """
        对外语音识别接口
        """
        self.wav_path = wav_path
        self.result_text = ""
        self._closed = False

        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )

        # 防止假死
        self.ws.run_forever(
            ping_interval=30,
            ping_timeout=10
        )

        return self.result_text
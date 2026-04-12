import json
import threading
import time
import websocket
import pyaudio
import base64

from src.config.settings import (
    XFYUN_ASR_APP_ID,
    XFYUN_ASR_API_KEY,
    XFYUN_ASR_API_SECRET
)
from src.utils.xfyun_auth import create_ws_url


class XFYunMicStreamASR:
    def __init__(self, on_partial=None, on_final=None):
        self.on_partial = on_partial
        self.on_final = on_final
        self.ws = None
        self.running = False
        self.audio_running = False

    def start(self):
        ws_url = create_ws_url(
            XFYUN_ASR_API_KEY,
            XFYUN_ASR_API_SECRET
        )

        self.ws = websocket.WebSocketApp(
            ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )

        self.running = True
        self.ws.run_forever()

    # ================= WebSocket =================

    def _on_open(self, ws):
        print("🎤 已连接，请说一句完整的话")

        # 1️⃣ 首帧（必须）
        first_frame = {
            "common": {"app_id": XFYUN_ASR_APP_ID},
            "business": {
                "language": "zh_cn",
                "domain": "iat",
                "accent": "mandarin",
                "vad_eos": 2000
            },
            "data": {
                "status": 0,
                "format": "audio/L16;rate=16000",
                "encoding": "raw",
                "audio": ""
            }
        }
        ws.send(json.dumps(first_frame))

        # 2️⃣ 启动音频线程
        self.audio_running = True
        threading.Thread(
            target=self._send_audio,
            daemon=True
        ).start()

    def _send_audio(self):
        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1280
        )

        try:
            while self.audio_running:
                audio = stream.read(1280, exception_on_overflow=False)
                frame = {
                    "data": {
                        "status": 1,
                        "format": "audio/L16;rate=16000",
                        "encoding": "raw",
                        "audio": base64.b64encode(audio).decode()
                    }
                }
                self.ws.send(json.dumps(frame))
                time.sleep(0.04)

        except Exception as e:
            print("❌ 音频线程异常:", e)

        finally:
            try:
                end_frame = {
                    "data": {
                        "status": 2,
                        "format": "audio/L16;rate=16000",
                        "encoding": "raw",
                        "audio": ""
                    }
                }
                self.ws.send(json.dumps(end_frame))
            except:
                pass

            stream.stop_stream()
            stream.close()
            p.terminate()

    def _on_message(self, ws, message):
        msg = json.loads(message)

        if msg.get("code", 0) != 0:
            print("❌ ASR 错误:", msg)
            self._stop()
            return

        if "data" not in msg or "result" not in msg["data"]:
            return

        result = msg["data"]["result"]
        text = "".join(
            w["w"] for ws_item in result["ws"] for w in ws_item["cw"]
        )

        if result.get("ls"):  # ✅ 最终结果
            if self.on_final:
                self.on_final(text)

            # 🔴 关键：一句话结束，立刻收尾
            self._stop()
        else:
            if self.on_partial:
                self.on_partial(text)

    def _stop(self):
        self.audio_running = False
        self.running = False
        try:
            self.ws.close()
        except:
            pass

    def _on_error(self, ws, error):
        print("⚠️ WebSocket 错误:", error)

    def _on_close(self, ws, *args):
        print("🔚 ASR 连接关闭（正常）")
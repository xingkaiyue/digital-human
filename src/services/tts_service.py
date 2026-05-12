from __future__ import annotations

import io
import os
import re
import wave
from typing import Optional

from dotenv import load_dotenv

from utils.xfyun_tts_ws import XFYunRealtimeTTS


load_dotenv()


class XFYunTTSService:
    """
    改进版：
    1. 增加 voice alias，确保 xiaolu / lingfeizhe 能稳定映射
    2. 长文本按句切分，降低机械感
    3. PCM/WAV 输出时增加句间静音和尾部静音，改善吞尾
    4. WAV 返回真实 wav 文件，而不是裸 PCM
    """

    VOICE_ALIAS = {
        "xiaolu": "xiaolu",
        "小露": "xiaolu",
        "lingfeizhe": "lingfeizhe",
        "聆飞哲": "lingfeizhe",
    }

    def __init__(
        self,
        voice: Optional[str] = None,
        speed: int = 50,
        volume: int = 50,
        pitch: int = 50,
        pcm_sample_rate: int = 16000,
    ):
        self.voice = self._normalize_voice(voice or os.getenv("XFYUN_TTS_VOICE", "xiaolu"))
        self.speed = speed
        self.volume = volume
        self.pitch = pitch
        self.pcm_sample_rate = pcm_sample_rate

        self.appid = os.getenv("XFYUN_TTS_APP_ID", "").strip()
        self.api_key = os.getenv("XFYUN_TTS_API_KEY", "").strip()
        self.api_secret = os.getenv("XFYUN_TTS_API_SECRET", "").strip()

        if not self.appid:
            raise ValueError("XFYUN_TTS_APP_ID is required")
        if not self.api_key:
            raise ValueError("XFYUN_TTS_API_KEY is required")
        if not self.api_secret:
            raise ValueError("XFYUN_TTS_API_SECRET is required")

        self.client = XFYunRealtimeTTS(
            appid=self.appid,
            api_key=self.api_key,
            api_secret=self.api_secret,
        )

    def synthesize_bytes(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[int] = None,
        volume: Optional[int] = None,
        pitch: Optional[int] = None,
        audio_format: str = "mp3",
    ) -> bytes:
        text = (text or "").strip()
        if not text:
            raise ValueError("text must not be empty")

        final_voice = self._normalize_voice(voice or self.voice)
        final_speed = self._clamp(speed if speed is not None else self.speed, 0, 100)
        final_volume = self._clamp(volume if volume is not None else self.volume, 0, 100)
        final_pitch = self._clamp(pitch if pitch is not None else self.pitch, 0, 100)

        normalized_audio_format = (audio_format or "mp3").strip().lower()

        print(
            "TTS synthesize ->",
            {
                "voice": final_voice,
                "speed": final_speed,
                "volume": final_volume,
                "pitch": final_pitch,
                "audio_format": normalized_audio_format,
            },
        )

        # mp3 优先整段合成，避免直接拼接多个 mp3 带来的兼容问题
        if normalized_audio_format == "mp3":
            synth_text = self._prepare_text_for_tts(text)
            audio = self._synthesize_single_segment(
                text=synth_text,
                voice=final_voice,
                speed=final_speed,
                volume=final_volume,
                pitch=final_pitch,
                audio_format="mp3",
            )
            self._validate_audio_bytes(audio)
            return audio

        # wav / pcm / raw 走“分句合成 + 静音拼接”
        segments = self._split_text_for_tts(text)
        if not segments:
            raise ValueError("No valid text segments for TTS")

        pcm_parts: list[bytes] = []

        for idx, seg in enumerate(segments):
            seg_text = self._prepare_text_for_tts(seg)

            pcm_audio = self._synthesize_single_segment(
                text=seg_text,
                voice=final_voice,
                speed=final_speed,
                volume=final_volume,
                pitch=final_pitch,
                audio_format="pcm",
            )
            self._validate_audio_bytes(pcm_audio)
            pcm_parts.append(pcm_audio)

            # 句间静音，减少机械感
            if idx < len(segments) - 1:
                pcm_parts.append(self._build_pcm_silence(duration_ms=180))

        merged_pcm = b"".join(pcm_parts)

        # 尾部静音，解决最后一个字不完整
        merged_pcm += self._build_pcm_silence(duration_ms=420)

        if normalized_audio_format in {"pcm", "raw"}:
            return merged_pcm

        if normalized_audio_format == "wav":
            return self._wrap_pcm_to_wav(
                pcm_bytes=merged_pcm,
                sample_rate=self.pcm_sample_rate,
                sample_width=2,
                channels=1,
            )

        raise ValueError(f"Unsupported audio_format: {normalized_audio_format}")

    def synthesize_to_file(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        speed: Optional[int] = None,
        volume: Optional[int] = None,
        pitch: Optional[int] = None,
        audio_format: str = "mp3",
    ) -> str:
        audio = self.synthesize_bytes(
            text=text,
            voice=voice,
            speed=speed,
            volume=volume,
            pitch=pitch,
            audio_format=audio_format,
        )

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, "wb") as f:
            f.write(audio)

        return output_path

    def get_content_type(self, audio_format: str = "mp3") -> str:
        normalized_audio_format = (audio_format or "mp3").strip().lower()
        if normalized_audio_format == "mp3":
            return "audio/mpeg"
        if normalized_audio_format == "wav":
            return "audio/wav"
        if normalized_audio_format in {"pcm", "raw"}:
            return "application/octet-stream"
        return "application/octet-stream"

    def _synthesize_single_segment(
        self,
        text: str,
        voice: str,
        speed: int,
        volume: int,
        pitch: int,
        audio_format: str,
    ) -> bytes:
        aue, auf = self._resolve_audio_params(audio_format)

        print(
            "TTS single segment ->",
            {
                "text": text,
                "voice": voice,
                "aue": aue,
                "auf": auf,
            },
        )

        audio = self.client.synthesize_bytes(
            text=text,
            voice=voice,
            speed=speed,
            volume=volume,
            pitch=pitch,
            aue=aue,
            auf=auf,
        )

        if isinstance(audio, bytearray):
            audio = bytes(audio)

        return audio

    def _prepare_text_for_tts(self, text: str) -> str:
        """
        轻量清洗 + 末尾补停顿，帮助改善吞尾。
        """
        text = re.sub(r"\s+", " ", (text or "").strip())
        if not text:
            return text

        if text[-1] in {"。", "！", "？", ".", "!", "?"}:
            return text + " "
        return text + "。 "

    def _split_text_for_tts(self, text: str) -> list[str]:
        """
        长文本切成较自然的小句，减少中段机械感。
        """
        text = re.sub(r"\s+", " ", (text or "").strip())
        if not text:
            return []

        first_parts = re.split(r"(?<=[。！？!?；;])", text)
        segments: list[str] = []

        for part in first_parts:
            part = part.strip()
            if not part:
                continue

            if len(part) <= 60:
                segments.append(part)
                continue

            second_parts = re.split(r"(?<=[，、,:：])", part)
            buf = ""

            for sp in second_parts:
                sp = sp.strip()
                if not sp:
                    continue

                if len(buf) + len(sp) <= 60:
                    buf += sp
                else:
                    if buf:
                        segments.append(buf)
                    buf = sp

            if buf:
                segments.append(buf)

        return segments

    def _normalize_voice(self, voice: Optional[str]) -> str:
        v = (voice or "").strip()
        if not v:
            return "xiaolu"
        return self.VOICE_ALIAS.get(v, v)

    def _resolve_audio_params(self, audio_format: str) -> tuple[str, str]:
        """
        统一把业务层 audio_format 映射成讯飞 websocket 所需参数：
        - aue: 编码方式
        - auf: 音频采样格式
        """
        if audio_format == "mp3":
            return "lame", f"audio/L16;rate={self.pcm_sample_rate}"

        if audio_format in {"wav", "pcm", "raw"}:
            return "raw", f"audio/L16;rate={self.pcm_sample_rate}"

        raise ValueError(f"Unsupported audio_format: {audio_format}")

    def _build_pcm_silence(
        self,
        duration_ms: int,
        sample_rate: Optional[int] = None,
        sample_width: int = 2,
        channels: int = 1,
    ) -> bytes:
        real_sample_rate = sample_rate or self.pcm_sample_rate
        frame_count = int(real_sample_rate * duration_ms / 1000)
        return b"\x00" * frame_count * sample_width * channels

    def _wrap_pcm_to_wav(
        self,
        pcm_bytes: bytes,
        sample_rate: int,
        sample_width: int,
        channels: int,
    ) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        return buf.getvalue()

    @staticmethod
    def _validate_audio_bytes(audio: bytes) -> None:
        if not isinstance(audio, bytes):
            raise TypeError(f"Expected bytes from XFYunRealtimeTTS, got {type(audio)}")
        if not audio:
            raise RuntimeError("TTS returned empty audio bytes")

    @staticmethod
    def _clamp(value: int, min_value: int, max_value: int) -> int:
        return max(min_value, min(max_value, int(value)))

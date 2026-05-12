from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from modules.asr import realtime_asr


if __name__ == "__main__":
    wav_path = Path(__file__).resolve().parent / "test.wav"
    print(realtime_asr(str(wav_path)))

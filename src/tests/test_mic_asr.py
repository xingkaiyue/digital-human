from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from modules.asr import XFYunMicStreamASR


def on_partial(text: str) -> None:
    print(f"partial: {text}")


def on_final(text: str) -> None:
    print(f"final: {text}")


if __name__ == "__main__":
    asr = XFYunMicStreamASR(on_partial=on_partial, on_final=on_final)
    asr.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        asr.stop()

"""
screenshot.py - 스크린샷 캡처 스크립트

사용법:
    python screenshot.py [monitor] [output]

인수:
    monitor  : 모니터 번호 (0=전체, 1=첫번째, 2=두번째, ...) 기본값: 0
    output   : 저장 경로 (기본값: screenshot_YYYYMMDD_HHMMSS.png)

예시:
    python screenshot.py          # 전체 화면
    python screenshot.py 1        # 첫번째 모니터
    python screenshot.py 2 out.png
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path


def take_screenshot(monitor: int = 0, output: str | None = None) -> str:
    try:
        import mss
        import mss.tools
    except ImportError:
        print("mss 패키지가 필요합니다: pip install mss")
        sys.exit(1)

    if output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = f"screenshot_{ts}.png"

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with mss.mss() as sct:
        monitors = sct.monitors  # [0]=전체, [1]=첫번째, ...
        if monitor >= len(monitors):
            print(f"모니터 {monitor}이 없습니다. 사용 가능: 0~{len(monitors)-1}")
            sys.exit(1)
        region = monitors[monitor]
        img = sct.grab(region)
        mss.tools.to_png(img.rgb, img.size, output=str(output_path))

    print(f"저장됨: {output_path.resolve()}")
    return str(output_path.resolve())


if __name__ == "__main__":
    mon = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    out = sys.argv[2] if len(sys.argv) > 2 else None
    take_screenshot(mon, out)

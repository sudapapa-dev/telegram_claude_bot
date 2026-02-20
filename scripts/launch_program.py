"""
launch_program.py - 프로그램 실행 스크립트

사용법:
    python launch_program.py <program_name> [args...]

인수:
    program_name : 실행할 프로그램 이름 또는 경로
                   - 이름만 입력 시 PATH, 시작 메뉴, 일반 경로에서 검색
                   - 전체 경로 입력 시 직접 실행

예시:
    python launch_program.py notepad
    python launch_program.py chrome
    python launch_program.py "C:\\Program Files\\...\\app.exe"
    python launch_program.py code D:\\myproject
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# 일반적인 프로그램 검색 경로 (Windows)
SEARCH_PATHS = [
    Path("C:/Program Files"),
    Path("C:/Program Files (x86)"),
    Path(Path.home(), "AppData/Local"),
    Path(Path.home(), "AppData/Local/Programs"),
    Path("C:/Windows/System32"),
]

COMMON_ALIASES = {
    "chrome": ["chrome.exe", "Google/Chrome/Application/chrome.exe"],
    "firefox": ["firefox.exe", "Mozilla Firefox/firefox.exe"],
    "code": ["Code.exe", "Microsoft VS Code/Code.exe"],
    "notepad": ["notepad.exe"],
    "explorer": ["explorer.exe"],
    "calc": ["calc.exe"],
    "cmd": ["cmd.exe"],
    "powershell": ["powershell.exe"],
    "taskmgr": ["Taskmgr.exe"],
}


def find_program(name: str) -> str | None:
    # 1. 직접 실행 가능한지 (PATH)
    found = shutil.which(name)
    if found:
        return found

    # 2. 전체 경로인지
    p = Path(name)
    if p.exists():
        return str(p)

    # 3. 별칭 매핑
    lower = name.lower()
    candidates = COMMON_ALIASES.get(lower, [f"{name}.exe", name])

    for search_root in SEARCH_PATHS:
        if not search_root.exists():
            continue
        for candidate in candidates:
            full = search_root / candidate
            if full.exists():
                return str(full)
        # 재귀 검색 (최대 2단계)
        for candidate in candidates:
            matches = list(search_root.rglob(candidate))
            if matches:
                return str(matches[0])

    return None


def launch(name: str, args: list[str]) -> None:
    path = find_program(name)
    if not path:
        print(f"프로그램을 찾을 수 없습니다: {name}")
        sys.exit(1)

    cmd = [path] + args
    print(f"실행: {' '.join(cmd)}")
    subprocess.Popen(cmd, shell=False)
    print("실행됨")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python launch_program.py <program_name> [args...]")
        sys.exit(1)
    launch(sys.argv[1], sys.argv[2:])

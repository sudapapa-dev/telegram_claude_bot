"""
find_process.py - 실행 중인 프로세스 검색 스크립트

사용법:
    python find_process.py [keyword]

인수:
    keyword : 검색어 (프로세스 이름 또는 명령줄 포함 검색, 생략 시 전체 출력)

예시:
    python find_process.py           # 전체 프로세스 목록
    python find_process.py chrome    # 이름에 'chrome' 포함
    python find_process.py python    # python 프로세스 검색
"""
from __future__ import annotations

import sys


def find_processes(keyword: str = "") -> None:
    try:
        import psutil
    except ImportError:
        print("psutil 패키지가 필요합니다: pip install psutil")
        sys.exit(1)

    keyword_lower = keyword.lower()
    results = []

    for proc in psutil.process_iter(["pid", "name", "status", "cmdline", "memory_info"]):
        try:
            info = proc.info
            name = info["name"] or ""
            cmdline = " ".join(info["cmdline"] or [])

            if keyword_lower and keyword_lower not in name.lower() and keyword_lower not in cmdline.lower():
                continue

            mem_mb = info["memory_info"].rss / (1024 * 1024) if info["memory_info"] else 0
            results.append({
                "pid": info["pid"],
                "name": name,
                "status": info["status"],
                "mem_mb": mem_mb,
                "cmdline": cmdline[:120],
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not results:
        print(f"'{keyword}' 에 해당하는 프로세스가 없습니다.")
        return

    print(f"{'PID':>7}  {'이름':<30}  {'상태':<10}  {'메모리(MB)':>10}  명령줄")
    print("-" * 100)
    for r in sorted(results, key=lambda x: x["mem_mb"], reverse=True):
        print(f"{r['pid']:>7}  {r['name']:<30}  {r['status']:<10}  {r['mem_mb']:>10.1f}  {r['cmdline']}")

    print(f"\n총 {len(results)}개 프로세스")


if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 else ""
    find_processes(kw)

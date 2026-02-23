#!/usr/bin/env python3
"""
HTML 파일을 네임스페이스별로 병합하여 MD 파일로 저장

18,000개 파일 → 약 20개 파일로 병합
"""

import os
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List

# .env 로딩
try:
    from dotenv import load_dotenv
    _script_dir = Path(__file__).parent
    _project_root = _script_dir.parent.parent.parent.parent
    _env_file = _project_root / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    pass

try:
    from bs4 import BeautifulSoup
    import html2text
    PREPROCESSING_AVAILABLE = True
except ImportError:
    PREPROCESSING_AVAILABLE = False
    print("pip install beautifulsoup4 html2text")
    sys.exit(1)


def convert_html_to_markdown(file_path: Path) -> str:
    """HTML을 Markdown으로 변환"""
    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
    except:
        content = file_path.read_text(encoding='cp1252', errors='ignore')

    soup = BeautifulSoup(content, 'html.parser')
    for element in soup(["script", "style", "meta", "link", "noscript", "iframe", "head", "footer"]):
        element.decompose()

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.ignore_tables = False
    h.body_width = 0

    return h.handle(str(soup))


def extract_namespace(filename: str) -> str:
    """파일명에서 네임스페이스 추출"""
    if 'Autodesk_AutoCAD_' in filename:
        parts = filename.split('Autodesk_AutoCAD_')
        if len(parts) > 1:
            sub = parts[1].split('_')[0]
            return f'Autodesk.AutoCAD.{sub}'
    return 'Other'


def merge_by_namespace(source_dir: Path, output_dir: Path) -> Dict[str, int]:
    """네임스페이스별로 HTML 파일을 병합하여 MD로 저장"""

    output_dir.mkdir(parents=True, exist_ok=True)

    # 파일을 네임스페이스별로 그룹화
    ns_files: Dict[str, List[Path]] = defaultdict(list)

    html_files = list(source_dir.glob('*.html')) + list(source_dir.glob('*.htm'))
    print(f"총 {len(html_files)}개 HTML 파일 발견")

    for f in html_files:
        ns = extract_namespace(f.stem)
        ns_files[ns].append(f)

    print(f"{len(ns_files)}개 네임스페이스로 분류됨\n")

    results = {}

    for ns, files in sorted(ns_files.items()):
        # 파일명 생성: Autodesk.AutoCAD.DatabaseServices -> DatabaseServices.md
        short_name = ns.replace('Autodesk.AutoCAD.', '') if ns.startswith('Autodesk.AutoCAD.') else ns
        output_file = output_dir / f"{short_name}.md"

        print(f"병합 중: {ns} ({len(files)}개 파일) -> {output_file.name}")

        merged_content = []
        merged_content.append(f"# {ns}\n\n")
        merged_content.append(f"이 문서는 {ns} 네임스페이스의 API 레퍼런스입니다.\n\n")
        merged_content.append("---\n\n")

        # 파일명 기준 정렬
        for f in sorted(files, key=lambda x: x.stem):
            try:
                md = convert_html_to_markdown(f)
                if md.strip():
                    merged_content.append(f"## {f.stem}\n\n")
                    merged_content.append(md)
                    merged_content.append("\n\n---\n\n")
            except Exception as e:
                print(f"  경고: {f.name} 변환 실패 - {e}")

        # 저장
        output_file.write_text(''.join(merged_content), encoding='utf-8')
        file_size = output_file.stat().st_size / 1024 / 1024
        results[ns] = len(files)
        print(f"  -> {output_file.name} ({file_size:.2f} MB)\n")

    return results


def main():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent.parent.parent

    source_dir = project_root / "data" / "chm" / "arxmgd"
    output_dir = project_root / "data" / "chm" / "arxmgd_merged"

    if not source_dir.exists():
        print(f"소스 디렉토리가 없습니다: {source_dir}")
        sys.exit(1)

    print("=" * 60)
    print("네임스페이스별 HTML 병합 시작")
    print("=" * 60)
    print(f"소스: {source_dir}")
    print(f"출력: {output_dir}\n")

    results = merge_by_namespace(source_dir, output_dir)

    print("=" * 60)
    print("병합 완료!")
    print(f"총 {sum(results.values())}개 파일 -> {len(results)}개 MD 파일")
    print("=" * 60)

    # 총 크기 계산
    total_size = sum(f.stat().st_size for f in output_dir.glob('*.md'))
    print(f"총 크기: {total_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()

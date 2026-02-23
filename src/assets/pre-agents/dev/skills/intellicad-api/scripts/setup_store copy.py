#!/usr/bin/env python3
"""
Google File Search Store 설정 및 문서 업로드 스크립트

AutoCAD SDK CHM 문서를 Google File Search Store에 업로드하여
RAG 검색이 가능하도록 설정합니다.
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

# .env 파일 자동 로딩
try:
    from dotenv import load_dotenv
    # 스크립트 위치 기준으로 프로젝트 루트의 .env 파일 로드
    _script_dir = Path(__file__).parent
    _project_root = _script_dir.parent.parent.parent.parent
    _env_file = _project_root / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    pass  # python-dotenv가 없으면 무시 (환경 변수 직접 설정 필요)

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


# 설정
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent.parent.parent  # .claude/skills/intellicad-api/scripts -> project root
CONFIG_DIR = script_dir.parent / "config"
CONFIG_FILE = CONFIG_DIR / "store_config.json"

# 지원되는 문서 확장자
SUPPORTED_EXTENSIONS = {
    '.txt', '.md', '.html', '.htm',
    '.pdf', '.doc', '.docx',
    '.csv', '.xlsx', '.xls',
    '.py', '.js', '.cs', '.java', '.cpp', '.h'
}

# 기본 Store 이름
DEFAULT_STORE_DISPLAY_NAME = "autocad-sdk-docs"


def load_config() -> Dict:
    """설정 파일을 로드합니다."""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    return {}


def save_config(config: Dict):
    """설정 파일을 저장합니다."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding='utf-8')


def get_client():
    """Google GenAI 클라이언트를 생성합니다."""
    if not GENAI_AVAILABLE:
        raise ImportError(
            "google-genai 패키지가 설치되지 않았습니다.\n"
            "설치: pip install google-genai"
        )

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError(
            "GOOGLE_API_KEY 환경 변수가 설정되지 않았습니다.\n"
            "설정: export GOOGLE_API_KEY='your-api-key'"
        )

    return genai.Client(api_key=api_key)


def create_store(display_name: str = DEFAULT_STORE_DISPLAY_NAME) -> Dict[str, Any]:
    """
    새 File Search Store를 생성합니다.

    Args:
        display_name: Store 표시 이름

    Returns:
        생성된 Store 정보
    """
    client = get_client()

    try:
        store = client.file_search_stores.create(
            config={'display_name': display_name}
        )

        # 설정 저장
        config = load_config()
        config['default_store'] = store.name
        config['stores'] = config.get('stores', {})
        config['stores'][display_name] = {
            'name': store.name,
            'display_name': display_name,
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        save_config(config)

        return {
            "success": True,
            "store_name": store.name,
            "display_name": display_name
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def upload_file(
    file_path: Path,
    store_name: str,
    display_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    파일을 File Search Store에 업로드합니다.

    Args:
        file_path: 업로드할 파일 경로
        store_name: Store 이름
        display_name: 파일 표시 이름 (기본값: 파일명)

    Returns:
        업로드 결과
    """
    client = get_client()

    if not display_name:
        display_name = file_path.name

    try:
        operation = client.file_search_stores.upload_to_file_search_store(
            file=str(file_path),
            file_search_store_name=store_name,
            config={
                'display_name': display_name
            }
        )

        # 완료 대기
        while not operation.done:
            time.sleep(2)
            operation = client.operations.get(operation)

        return {
            "success": True,
            "file": str(file_path),
            "display_name": display_name
        }

    except Exception as e:
        return {
            "success": False,
            "file": str(file_path),
            "error": str(e)
        }


def upload_directory(
    directory: Path,
    store_name: str,
    recursive: bool = True,
    max_workers: int = 4
) -> Dict[str, Any]:
    """
    디렉토리 내 모든 지원 파일을 업로드합니다.

    Args:
        directory: 업로드할 디렉토리
        store_name: Store 이름
        recursive: 하위 디렉토리 포함 여부
        max_workers: 동시 업로드 워커 수

    Returns:
        업로드 결과 요약
    """
    # 파일 목록 수집
    if recursive:
        files = list(directory.rglob("*"))
    else:
        files = list(directory.glob("*"))

    # 지원되는 파일만 필터링
    files = [
        f for f in files
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    if not files:
        return {
            "success": False,
            "error": f"지원되는 파일이 없습니다: {directory}"
        }

    print(f"📁 {len(files)}개 파일 업로드 시작...")

    results = {
        "success": True,
        "total": len(files),
        "uploaded": 0,
        "failed": 0,
        "errors": []
    }

    # 병렬 업로드
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(upload_file, f, store_name): f
            for f in files
        }

        for future in as_completed(futures):
            file_path = futures[future]
            result = future.result()

            if result["success"]:
                results["uploaded"] += 1
                print(f"  ✅ {file_path.name}")
            else:
                results["failed"] += 1
                results["errors"].append({
                    "file": str(file_path),
                    "error": result.get("error", "Unknown error")
                })
                print(f"  ❌ {file_path.name}: {result.get('error', 'Unknown error')}")

    if results["failed"] > 0:
        results["success"] = False

    return results


def upload_chm_extracted(
    chm_dir: Path,
    store_name: str
) -> Dict[str, Any]:
    """
    CHM에서 추출된 HTML 파일들을 업로드합니다.
    기존 ingester로 추출된 data/chm/ 디렉토리 구조를 사용합니다.

    Args:
        chm_dir: CHM 추출 디렉토리 (예: data/chm/arxmgd)
        store_name: Store 이름

    Returns:
        업로드 결과
    """
    if not chm_dir.exists():
        return {
            "success": False,
            "error": f"디렉토리가 존재하지 않습니다: {chm_dir}"
        }

    # HTML/HTM 파일만 업로드
    html_files = list(chm_dir.rglob("*.html")) + list(chm_dir.rglob("*.htm"))

    if not html_files:
        return {
            "success": False,
            "error": f"HTML 파일이 없습니다: {chm_dir}"
        }

    print(f"📚 CHM 문서 업로드: {chm_dir.name} ({len(html_files)}개 파일)")

    return upload_directory(chm_dir, store_name, recursive=True)


def list_stores() -> Dict[str, Any]:
    """사용 가능한 Store 목록을 반환합니다."""
    try:
        client = get_client()
        stores = list(client.file_search_stores.list())

        store_list = []
        for store in stores:
            store_list.append({
                "name": store.name,
                "display_name": getattr(store, 'display_name', 'N/A')
            })

        return {
            "success": True,
            "stores": store_list
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def delete_store(store_name: str) -> Dict[str, Any]:
    """Store를 삭제합니다."""
    try:
        client = get_client()
        client.file_search_stores.delete(name=store_name)

        # 설정에서도 제거
        config = load_config()
        if config.get('default_store') == store_name:
            config['default_store'] = None

        stores = config.get('stores', {})
        for display_name, store_info in list(stores.items()):
            if store_info.get('name') == store_name:
                del stores[display_name]

        save_config(config)

        return {
            "success": True,
            "deleted": store_name
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def init_default_store() -> Dict[str, Any]:
    """
    기본 Store를 생성하고 기본 문서를 업로드합니다.
    """
    print("🚀 IntelliCAD API Skill 초기화 시작...\n")

    # 1. Store 생성
    print("1️⃣ File Search Store 생성...")
    create_result = create_store(DEFAULT_STORE_DISPLAY_NAME)

    if not create_result["success"]:
        return create_result

    store_name = create_result["store_name"]
    print(f"   ✅ Store 생성 완료: {store_name}\n")

    # 2. CHM 문서 업로드 (있는 경우)
    chm_dirs = [
        project_root / "data" / "chm" / "arxmgd",
        project_root / "data" / "chm" / "arxdev",
    ]

    uploaded_sources = []
    for chm_dir in chm_dirs:
        if chm_dir.exists():
            print(f"2️⃣ CHM 문서 업로드: {chm_dir.name}...")
            result = upload_chm_extracted(chm_dir, store_name)
            if result["success"]:
                uploaded_sources.append(chm_dir.name)
                print(f"   ✅ {result['uploaded']}/{result['total']} 파일 업로드 완료\n")
            else:
                print(f"   ⚠️ 일부 파일 업로드 실패: {result.get('error', '')}\n")

    if not uploaded_sources:
        print("   ℹ️ CHM 추출 파일이 없습니다.")
        print("   먼저 다음 명령으로 CHM 파일을 추출하세요:")
        print("   7z x data/chm/arxmgd.chm -odata/chm/arxmgd/\n")

    print("=" * 50)
    print("✅ 초기화 완료!")
    print(f"   Store: {store_name}")
    print(f"   업로드된 소스: {', '.join(uploaded_sources) if uploaded_sources else '없음'}")
    print("\n사용법:")
    print("   python search_api.py --query \"Line 객체 생성 방법\"")
    print("=" * 50)

    return {
        "success": True,
        "store_name": store_name,
        "uploaded_sources": uploaded_sources
    }


def show_status():
    """현재 설정 상태를 표시합니다."""
    config = load_config()

    print("\n📊 IntelliCAD API Skill 상태\n")
    print("=" * 50)

    if config.get('default_store'):
        print(f"✅ 기본 Store: {config['default_store']}")
    else:
        print("❌ 기본 Store 설정되지 않음")

    stores = config.get('stores', {})
    if stores:
        print(f"\n📁 등록된 Store ({len(stores)}개):")
        for display_name, info in stores.items():
            print(f"   - {display_name}: {info.get('name', 'N/A')}")
    else:
        print("\n📁 등록된 Store 없음")

    api_key = os.environ.get("GOOGLE_API_KEY")
    if api_key:
        print(f"\n🔑 GOOGLE_API_KEY: 설정됨 ({api_key[:8]}...)")
    else:
        print("\n🔑 GOOGLE_API_KEY: ❌ 설정되지 않음")

    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="Google File Search Store 설정 및 문서 업로드"
    )

    subparsers = parser.add_subparsers(dest='command', help='명령')

    # init 명령
    init_parser = subparsers.add_parser('init', help='기본 Store 생성 및 초기화')

    # create 명령
    create_parser = subparsers.add_parser('create', help='새 Store 생성')
    create_parser.add_argument('--name', type=str, default=DEFAULT_STORE_DISPLAY_NAME,
                              help='Store 표시 이름')

    # upload 명령
    upload_parser = subparsers.add_parser('upload', help='파일/디렉토리 업로드')
    upload_parser.add_argument('path', type=str, help='업로드할 파일 또는 디렉토리 경로')
    upload_parser.add_argument('--store', type=str, help='Store 이름 (기본값: 설정 파일)')

    # list 명령
    list_parser = subparsers.add_parser('list', help='Store 목록 조회')

    # delete 명령
    delete_parser = subparsers.add_parser('delete', help='Store 삭제')
    delete_parser.add_argument('store_name', type=str, help='삭제할 Store 이름')

    # status 명령
    status_parser = subparsers.add_parser('status', help='현재 상태 조회')

    # 단축 옵션
    parser.add_argument('--init', action='store_true', help='init 명령 단축')
    parser.add_argument('--status', action='store_true', help='status 명령 단축')

    args = parser.parse_args()

    # 단축 옵션 처리
    if args.init:
        args.command = 'init'
    elif args.status:
        args.command = 'status'

    # 명령 실행
    if args.command == 'init':
        result = init_default_store()
        if not result["success"]:
            print(f"\n❌ 초기화 실패: {result.get('error', 'Unknown error')}")
            sys.exit(1)

    elif args.command == 'create':
        result = create_store(args.name)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == 'upload':
        path = Path(args.path)
        store_name = args.store or load_config().get('default_store')

        if not store_name:
            print("❌ Store가 설정되지 않았습니다. --store 옵션을 사용하거나 init을 먼저 실행하세요.")
            sys.exit(1)

        if path.is_file():
            result = upload_file(path, store_name)
        else:
            result = upload_directory(path, store_name)

        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == 'list':
        result = list_stores()
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == 'delete':
        result = delete_store(args.store_name)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == 'status':
        show_status()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

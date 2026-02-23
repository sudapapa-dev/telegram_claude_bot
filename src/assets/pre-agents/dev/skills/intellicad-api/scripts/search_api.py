#!/usr/bin/env python3
"""
Google Gemini File Search API를 사용한 AutoCAD SDK 문서 RAG 검색

이 스크립트는 Google File Search Store에 업로드된 AutoCAD SDK 문서를
검색하고, IntelliCAD 호환 코드로 변환된 결과를 반환합니다.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any

# 현재 디렉토리를 path에 추가
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

# .env 파일 자동 로딩
try:
    from dotenv import load_dotenv
    _project_root = script_dir.parent.parent.parent.parent
    _env_file = _project_root / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    pass  # python-dotenv가 없으면 무시

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

from namespace_mapper import convert_namespace, extract_required_usings


# 설정
DEFAULT_MODEL = "gemini-2.5-flash"
CONFIG_FILE = script_dir.parent / "config" / "store_config.json"


def load_config() -> Dict:
    """저장소 설정을 로드합니다."""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    return {}


def save_config(config: Dict):
    """저장소 설정을 저장합니다."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
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


def search_documentation(
    query: str,
    store_name: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    convert_to_intellicad: bool = True
) -> Dict[str, Any]:
    """
    Google File Search를 사용하여 AutoCAD SDK 문서를 검색합니다.

    Args:
        query: 검색 쿼리
        store_name: File Search Store 이름 (None이면 설정 파일에서 로드)
        model: 사용할 Gemini 모델
        convert_to_intellicad: IntelliCAD 네임스페이스로 변환 여부

    Returns:
        검색 결과 딕셔너리
    """
    client = get_client()

    # Store 이름 확인
    if not store_name:
        config = load_config()
        store_name = config.get("default_store")

    if not store_name:
        return {
            "success": False,
            "error": "File Search Store가 설정되지 않았습니다. setup_store.py --init 실행 필요",
            "query": query
        }

    try:
        # File Search를 사용한 RAG 쿼리
        response = client.models.generate_content(
            model=model,
            contents=f"""AutoCAD .NET API 문서에서 다음 질문에 대한 정보를 찾아주세요:

질문: {query}

다음 형식으로 응답해주세요:
1. 관련 클래스/메서드 이름
2. 사용법 설명
3. C# 코드 예제 (있다면)
4. 관련 네임스페이스
5. 참고 문서 경로

코드 예제는 ```csharp 블록으로 감싸주세요.""",
            config=types.GenerateContentConfig(
                tools=[
                    types.Tool(
                        file_search=types.FileSearch(
                            file_search_store_names=[store_name]
                        )
                    )
                ]
            )
        )

        # 응답 처리
        answer_text = response.text

        # Citation 추출
        citations = []
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                metadata = candidate.grounding_metadata
                if hasattr(metadata, 'grounding_chunks'):
                    for chunk in metadata.grounding_chunks:
                        citations.append({
                            "source": getattr(chunk, 'source', 'unknown'),
                            "content": getattr(chunk, 'content', '')[:200]
                        })

        # IntelliCAD 변환
        converted_code = None
        warnings = []

        if convert_to_intellicad:
            # 코드 블록 추출 및 변환
            import re
            code_blocks = re.findall(r'```csharp\n(.*?)```', answer_text, re.DOTALL)

            if code_blocks:
                converted_blocks = []
                for block in code_blocks:
                    converted, block_warnings = convert_namespace(block)
                    converted_blocks.append(converted)
                    warnings.extend(block_warnings)

                converted_code = converted_blocks

                # 원본 응답에서 코드 블록 변환
                for original, converted in zip(code_blocks, converted_blocks):
                    answer_text = answer_text.replace(
                        f"```csharp\n{original}```",
                        f"```csharp\n{converted}```"
                    )

        return {
            "success": True,
            "query": query,
            "answer": answer_text,
            "converted_code": converted_code,
            "citations": citations,
            "warnings": warnings,
            "model": model,
            "store": store_name
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "query": query
        }


def search_class_info(class_name: str, **kwargs) -> Dict[str, Any]:
    """특정 클래스에 대한 정보를 검색합니다."""
    query = f"{class_name} class constructor methods properties AutoCAD .NET API"
    return search_documentation(query, **kwargs)


def search_method_info(class_name: str, method_name: str, **kwargs) -> Dict[str, Any]:
    """특정 메서드에 대한 정보를 검색합니다."""
    query = f"{class_name}.{method_name} method parameters return type example"
    return search_documentation(query, **kwargs)


def search_code_example(task_description: str, **kwargs) -> Dict[str, Any]:
    """특정 작업에 대한 코드 예제를 검색합니다."""
    query = f"How to {task_description} in AutoCAD .NET API C# code example"
    return search_documentation(query, **kwargs)


def list_stores() -> Dict[str, Any]:
    """사용 가능한 File Search Store 목록을 반환합니다."""
    try:
        client = get_client()
        stores = client.file_search_stores.list()

        store_list = []
        for store in stores:
            store_list.append({
                "name": store.name,
                "display_name": getattr(store, 'display_name', 'N/A'),
                "create_time": str(getattr(store, 'create_time', 'N/A'))
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


def main():
    parser = argparse.ArgumentParser(
        description="AutoCAD SDK 문서 RAG 검색 (Google File Search)"
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        help="검색 쿼리"
    )
    parser.add_argument(
        "--class", "-c",
        dest="class_name",
        type=str,
        help="검색할 클래스 이름"
    )
    parser.add_argument(
        "--method", "-m",
        type=str,
        help="검색할 메서드 이름 (--class와 함께 사용)"
    )
    parser.add_argument(
        "--example", "-e",
        type=str,
        help="코드 예제 검색 (작업 설명)"
    )
    parser.add_argument(
        "--store", "-s",
        type=str,
        help="File Search Store 이름"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"사용할 모델 (기본값: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--no-convert",
        action="store_true",
        help="IntelliCAD 네임스페이스 변환 비활성화"
    )
    parser.add_argument(
        "--list-stores",
        action="store_true",
        help="사용 가능한 Store 목록 출력"
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="JSON 형식으로 출력"
    )

    args = parser.parse_args()

    # Store 목록 출력
    if args.list_stores:
        result = list_stores()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # 검색 옵션
    search_kwargs = {
        "store_name": args.store,
        "model": args.model,
        "convert_to_intellicad": not args.no_convert
    }

    # 검색 수행
    if args.class_name and args.method:
        result = search_method_info(args.class_name, args.method, **search_kwargs)
    elif args.class_name:
        result = search_class_info(args.class_name, **search_kwargs)
    elif args.example:
        result = search_code_example(args.example, **search_kwargs)
    elif args.query:
        result = search_documentation(args.query, **search_kwargs)
    else:
        parser.print_help()
        return

    # 출력
    if args.raw:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result["success"]:
            print(f"\n📚 검색 쿼리: {result['query']}\n")
            print("=" * 60)
            print(result["answer"])
            print("=" * 60)

            if result.get("warnings"):
                print("\n⚠️ 호환성 경고:")
                for w in result["warnings"]:
                    print(f"  {w}")

            if result.get("citations"):
                print("\n📌 출처:")
                for c in result["citations"]:
                    print(f"  - {c['source']}")
        else:
            print(f"\n❌ 오류: {result['error']}")


if __name__ == "__main__":
    main()

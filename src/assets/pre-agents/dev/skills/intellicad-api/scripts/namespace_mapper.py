#!/usr/bin/env python3
"""
ObjectARX.NET to ObjectIRX.NET Namespace Mapper

AutoCAD SDK 코드를 IntelliCAD 호환 코드로 변환합니다.
"""

import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional


# ObjectARX.NET → ObjectIRX.NET 네임스페이스 매핑
NAMESPACE_MAP: Dict[str, str] = {
    # Core namespaces
    "Autodesk.AutoCAD.ApplicationServices": "IntelliCAD.ApplicationServices",
    "Autodesk.AutoCAD.DatabaseServices": "IntelliCAD.DatabaseServices",
    "Autodesk.AutoCAD.EditorInput": "IntelliCAD.EditorInput",
    "Autodesk.AutoCAD.Geometry": "IntelliCAD.Geometry",
    "Autodesk.AutoCAD.Runtime": "IntelliCAD.Runtime",

    # Additional namespaces
    "Autodesk.AutoCAD.Colors": "IntelliCAD.Colors",
    "Autodesk.AutoCAD.GraphicsInterface": "IntelliCAD.GraphicsInterface",
    "Autodesk.AutoCAD.GraphicsSystem": "IntelliCAD.GraphicsSystem",
    "Autodesk.AutoCAD.LayerManager": "IntelliCAD.LayerManager",
    "Autodesk.AutoCAD.Interop": "IntelliCAD.Interop",
    "Autodesk.AutoCAD.Interop.Common": "IntelliCAD.Interop.Common",
    "Autodesk.AutoCAD.PlottingServices": "IntelliCAD.PlottingServices",
    "Autodesk.AutoCAD.Publishing": "IntelliCAD.Publishing",
    "Autodesk.AutoCAD.BoundaryRepresentation": "IntelliCAD.BoundaryRepresentation",

    # Short form aliases (using statements)
    "Autodesk.AutoCAD": "IntelliCAD",
}

# IntelliCAD에서 지원되지 않거나 다르게 동작하는 API
INCOMPATIBLE_APIS: Dict[str, str] = {
    "Autodesk.AutoCAD.Windows": "IntelliCAD Windows UI - 버전에 따라 다름, 기본 WinForms 사용 권장",
    "Autodesk.AutoCAD.Ribbon": "IntelliCAD Ribbon - 버전에 따라 지원 여부 확인 필요",
    "Autodesk.AutoCAD.AcInfoCenterConn": "InfoCenter - IntelliCAD 미지원",
    "Autodesk.AutoCAD.WebServices": "Web Services - IntelliCAD 미지원",
    "AcadApplication": "COM 인터페이스 - IntelliCAD.Interop.IcadApplication 사용",
    "AcadDocument": "COM 인터페이스 - IntelliCAD.Interop.IcadDocument 사용",
}

# 클래스명 매핑 (필요한 경우)
CLASS_MAP: Dict[str, str] = {
    # 대부분의 클래스명은 동일하지만, 필요시 여기에 추가
    # "AcadClass": "IcadClass",
}


def convert_namespace(code: str) -> Tuple[str, List[str]]:
    """
    AutoCAD 네임스페이스를 IntelliCAD로 변환합니다.

    Args:
        code: 변환할 C# 코드 문자열

    Returns:
        (변환된 코드, 경고 메시지 리스트)
    """
    warnings = []
    result = code

    # 1. 호환되지 않는 API 체크
    for api, message in INCOMPATIBLE_APIS.items():
        if api in result:
            warnings.append(f"⚠️ 호환성 주의: {api} - {message}")

    # 2. 네임스페이스 변환 (긴 것부터 처리하여 부분 매칭 방지)
    sorted_namespaces = sorted(NAMESPACE_MAP.keys(), key=len, reverse=True)
    for autocad_ns in sorted_namespaces:
        intellicad_ns = NAMESPACE_MAP[autocad_ns]
        result = result.replace(autocad_ns, intellicad_ns)

    # 3. 클래스명 변환
    for autocad_class, intellicad_class in CLASS_MAP.items():
        # 단어 경계를 고려한 치환
        pattern = rf'\b{re.escape(autocad_class)}\b'
        result = re.sub(pattern, intellicad_class, result)

    return result, warnings


def convert_using_statements(code: str) -> str:
    """
    using 문만 추출하여 변환합니다.
    """
    lines = code.split('\n')
    converted_lines = []

    for line in lines:
        if line.strip().startswith('using ') and 'Autodesk.AutoCAD' in line:
            converted_line, _ = convert_namespace(line)
            converted_lines.append(converted_line)
        else:
            converted_lines.append(line)

    return '\n'.join(converted_lines)


def extract_required_usings(code: str) -> List[str]:
    """
    코드에서 필요한 using 문을 추출합니다.
    """
    required_usings = set()

    # 일반적으로 사용되는 타입과 해당 네임스페이스
    type_to_namespace = {
        "Document": "IntelliCAD.ApplicationServices",
        "Application": "IntelliCAD.ApplicationServices",
        "DocumentManager": "IntelliCAD.ApplicationServices",
        "Database": "IntelliCAD.DatabaseServices",
        "Transaction": "IntelliCAD.DatabaseServices",
        "BlockTable": "IntelliCAD.DatabaseServices",
        "BlockTableRecord": "IntelliCAD.DatabaseServices",
        "Line": "IntelliCAD.DatabaseServices",
        "Circle": "IntelliCAD.DatabaseServices",
        "Arc": "IntelliCAD.DatabaseServices",
        "Polyline": "IntelliCAD.DatabaseServices",
        "Entity": "IntelliCAD.DatabaseServices",
        "DBObject": "IntelliCAD.DatabaseServices",
        "OpenMode": "IntelliCAD.DatabaseServices",
        "Point3d": "IntelliCAD.Geometry",
        "Point2d": "IntelliCAD.Geometry",
        "Vector3d": "IntelliCAD.Geometry",
        "Matrix3d": "IntelliCAD.Geometry",
        "Editor": "IntelliCAD.EditorInput",
        "PromptPointOptions": "IntelliCAD.EditorInput",
        "PromptPointResult": "IntelliCAD.EditorInput",
        "PromptStatus": "IntelliCAD.EditorInput",
        "SelectionSet": "IntelliCAD.EditorInput",
        "CommandMethod": "IntelliCAD.Runtime",
        "Color": "IntelliCAD.Colors",
        "ColorIndex": "IntelliCAD.DatabaseServices",
    }

    for type_name, namespace in type_to_namespace.items():
        # 단어 경계를 고려한 검색
        if re.search(rf'\b{type_name}\b', code):
            required_usings.add(namespace)

    return sorted(list(required_usings))


def generate_intellicad_template(class_name: str, method_name: str = "Execute") -> str:
    """
    IntelliCAD 플러그인 기본 템플릿을 생성합니다.
    """
    template = f'''using IntelliCAD.ApplicationServices;
using IntelliCAD.DatabaseServices;
using IntelliCAD.EditorInput;
using IntelliCAD.Geometry;
using IntelliCAD.Runtime;

namespace MyIntelliCADPlugin
{{
    public class {class_name}
    {{
        [CommandMethod("{method_name}")]
        public void {method_name}()
        {{
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Database db = doc.Database;
            Editor ed = doc.Editor;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {{
                try
                {{
                    // TODO: 구현 코드 작성

                    tr.Commit();
                    ed.WriteMessage("\\n명령 실행 완료.");
                }}
                catch (System.Exception ex)
                {{
                    ed.WriteMessage($"\\n오류 발생: {{ex.Message}}");
                    tr.Abort();
                }}
            }}
        }}
    }}
}}
'''
    return template


def get_namespace_info() -> Dict:
    """
    네임스페이스 매핑 정보를 딕셔너리로 반환합니다.
    """
    return {
        "namespace_map": NAMESPACE_MAP,
        "incompatible_apis": INCOMPATIBLE_APIS,
        "class_map": CLASS_MAP,
    }


def main():
    parser = argparse.ArgumentParser(
        description="ObjectARX.NET to ObjectIRX.NET 변환기"
    )
    parser.add_argument(
        "--code", "-c",
        type=str,
        help="변환할 C# 코드 문자열"
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        help="변환할 C# 파일 경로"
    )
    parser.add_argument(
        "--template", "-t",
        type=str,
        help="생성할 클래스명 (템플릿 생성)"
    )
    parser.add_argument(
        "--info", "-i",
        action="store_true",
        help="네임스페이스 매핑 정보 출력"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="출력 파일 경로"
    )

    args = parser.parse_args()

    if args.info:
        info = get_namespace_info()
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return

    if args.template:
        template = generate_intellicad_template(args.template)
        if args.output:
            Path(args.output).write_text(template, encoding='utf-8')
            print(f"템플릿 생성 완료: {args.output}")
        else:
            print(template)
        return

    code = ""
    if args.code:
        code = args.code
    elif args.file:
        code = Path(args.file).read_text(encoding='utf-8')
    else:
        # stdin에서 읽기
        import sys
        code = sys.stdin.read()

    if not code:
        parser.print_help()
        return

    converted, warnings = convert_namespace(code)

    result = {
        "converted_code": converted,
        "warnings": warnings,
        "required_usings": extract_required_usings(converted)
    }

    if args.output:
        Path(args.output).write_text(converted, encoding='utf-8')
        print(f"변환 완료: {args.output}")
        if warnings:
            print("\n경고:")
            for w in warnings:
                print(f"  {w}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

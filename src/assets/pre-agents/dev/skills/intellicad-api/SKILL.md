---
name: intellicad-api-lookup
description: AutoCAD/IntelliCAD SDK 문서를 Google File Search로 검색하여 정확한 API 정보와 IntelliCAD 호환 C# 코드를 생성합니다. CAD 객체 생성, API 사용법, 클래스/메서드 정보가 필요할 때 사용합니다.
---

# IntelliCAD API Documentation Skill

## Overview

이 Skill은 AutoCAD SDK 문서를 Google Gemini File Search API로 검색하여 정확한 API 정보를 제공하고, ObjectARX.NET 코드를 IntelliCAD ObjectIRX.NET 호환 코드로 자동 변환합니다.

## When to Use This Skill

다음과 같은 상황에서 이 Skill을 사용합니다:

- CAD 객체(Line, Circle, Arc, Polyline 등) 생성/수정 방법 질문
- AutoCAD/IntelliCAD .NET API 클래스, 메서드, 속성 조회
- DatabaseServices, Geometry, EditorInput 등 네임스페이스 관련 질문
- C# 플러그인 개발 시 API 사용 예제 필요
- 특정 CAD 기능 구현 방법 문의

## Architecture

```
[사용자 질문] → [Google File Search RAG] → [API 문서 검색]
                                              ↓
[IntelliCAD C# 코드] ← [네임스페이스 변환] ← [검색 결과 + Citation]
```

## Instructions

### Step 1: Analyze User Query

사용자 질문에서 다음을 파악합니다:
- 필요한 CAD 객체 타입 (Line, Circle, Block 등)
- 작업 유형 (생성, 수정, 삭제, 조회)
- 필요한 네임스페이스 (DatabaseServices, Geometry 등)

### Step 2: Search Documentation via Google File Search

검색 스크립트를 실행하여 관련 문서를 찾습니다:

```bash
python .claude/skills/intellicad-api/scripts/search_api.py --query "[SEARCH_QUERY]"
```

**검색 예시:**
- "AcDbLine constructor" → Line 객체 생성자 조회
- "BlockTableRecord append entity" → 엔티티 추가 방법
- "Transaction commit" → 트랜잭션 처리 방법

### Step 3: Convert to IntelliCAD Compatible Code

검색 결과의 ObjectARX.NET 코드를 ObjectIRX.NET으로 변환합니다:

```bash
python .claude/skills/intellicad-api/scripts/namespace_mapper.py --code "[CODE_SNIPPET]"
```

### Step 4: Generate Response

다음 형식으로 응답을 생성합니다:

1. **API 설명**: 클래스/메서드의 목적과 사용법
2. **IntelliCAD C# 코드**: 변환된 코드 예제
3. **Citation**: 문서 출처 (할루시네이션 방지)
4. **주의사항**: 호환성 이슈 또는 추가 고려사항

## Namespace Mapping (ObjectARX.NET → ObjectIRX.NET)

| AutoCAD (ObjectARX.NET) | IntelliCAD (ObjectIRX.NET) |
|-------------------------|----------------------------|
| `Autodesk.AutoCAD.ApplicationServices` | `IntelliCAD.ApplicationServices` |
| `Autodesk.AutoCAD.DatabaseServices` | `IntelliCAD.DatabaseServices` |
| `Autodesk.AutoCAD.EditorInput` | `IntelliCAD.EditorInput` |
| `Autodesk.AutoCAD.Geometry` | `IntelliCAD.Geometry` |
| `Autodesk.AutoCAD.Runtime` | `IntelliCAD.Runtime` |
| `Autodesk.AutoCAD.Colors` | `IntelliCAD.Colors` |
| `Autodesk.AutoCAD.GraphicsInterface` | `IntelliCAD.GraphicsInterface` |
| `Autodesk.AutoCAD.LayerManager` | `IntelliCAD.LayerManager` |

## Examples

### Example 1: Line 객체 생성

**User Question**: "Line을 생성하는 방법을 알려줘"

**Skill Process**:
1. Search: `python scripts/search_api.py --query "AcDbLine Line constructor Point3d"`
2. Convert: namespace 변환 적용
3. Response:

```csharp
using IntelliCAD.ApplicationServices;
using IntelliCAD.DatabaseServices;
using IntelliCAD.Geometry;
using IntelliCAD.Runtime;

[CommandMethod("CreateLine")]
public void CreateLine()
{
    Document doc = Application.DocumentManager.MdiActiveDocument;
    Database db = doc.Database;

    using (Transaction tr = db.TransactionManager.StartTransaction())
    {
        BlockTable bt = tr.GetObject(db.BlockTableId, OpenMode.ForRead) as BlockTable;
        BlockTableRecord btr = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite) as BlockTableRecord;

        // Line 생성: 시작점 (0,0,0) → 끝점 (100,100,0)
        Line line = new Line(new Point3d(0, 0, 0), new Point3d(100, 100, 0));

        btr.AppendEntity(line);
        tr.AddNewlyCreatedDBObject(line, true);
        tr.Commit();
    }
}
```

**Citation**: arxmgd.chm > Autodesk.AutoCAD.DatabaseServices > Line Class

### Example 2: Circle 객체 생성

**User Question**: "Circle 객체를 만들고 색상을 지정하고 싶어"

**Skill Process**:
1. Search: `python scripts/search_api.py --query "AcDbCircle Circle constructor radius ColorIndex"`
2. Convert: namespace 변환 적용
3. Response:

```csharp
using IntelliCAD.ApplicationServices;
using IntelliCAD.DatabaseServices;
using IntelliCAD.Geometry;
using IntelliCAD.Colors;
using IntelliCAD.Runtime;

[CommandMethod("CreateColoredCircle")]
public void CreateColoredCircle()
{
    Document doc = Application.DocumentManager.MdiActiveDocument;
    Database db = doc.Database;

    using (Transaction tr = db.TransactionManager.StartTransaction())
    {
        BlockTable bt = tr.GetObject(db.BlockTableId, OpenMode.ForRead) as BlockTable;
        BlockTableRecord btr = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite) as BlockTableRecord;

        // Circle 생성: 중심점 (50,50,0), 반지름 25
        Circle circle = new Circle();
        circle.Center = new Point3d(50, 50, 0);
        circle.Radius = 25;

        // 색상 지정 (빨간색 = ColorIndex 1)
        circle.ColorIndex = 1;

        btr.AppendEntity(circle);
        tr.AddNewlyCreatedDBObject(circle, true);
        tr.Commit();
    }
}
```

**Citation**: arxmgd.chm > Autodesk.AutoCAD.DatabaseServices > Circle Class

### Example 3: 사용자 입력 받기

**User Question**: "사용자로부터 점 좌표를 입력받아서 처리하고 싶어"

```csharp
using IntelliCAD.ApplicationServices;
using IntelliCAD.DatabaseServices;
using IntelliCAD.EditorInput;
using IntelliCAD.Geometry;
using IntelliCAD.Runtime;

[CommandMethod("GetUserPoint")]
public void GetUserPoint()
{
    Document doc = Application.DocumentManager.MdiActiveDocument;
    Editor ed = doc.Editor;

    // 사용자에게 점 입력 요청
    PromptPointOptions ppo = new PromptPointOptions("\n시작점을 선택하세요: ");
    ppo.AllowNone = false;

    PromptPointResult ppr = ed.GetPoint(ppo);

    if (ppr.Status == PromptStatus.OK)
    {
        Point3d startPoint = ppr.Value;
        ed.WriteMessage($"\n선택된 점: ({startPoint.X}, {startPoint.Y}, {startPoint.Z})");
    }
}
```

**Citation**: arxmgd.chm > Autodesk.AutoCAD.EditorInput > PromptPointOptions Class

## Output Format

항상 다음 형식으로 응답합니다:

1. **API 개요**: 요청된 기능에 대한 간략한 설명
2. **IntelliCAD C# 코드**: 완전한 실행 가능한 코드 예제
3. **주요 클래스/메서드**: 사용된 핵심 API 설명
4. **Citation**: 문서 출처 명시
5. **주의사항**: 호환성 이슈, 예외 처리, 추가 고려사항

## Incompatible APIs

다음 API들은 IntelliCAD에서 지원되지 않거나 다르게 동작할 수 있습니다:

- `Autodesk.AutoCAD.Windows.*` - AutoCAD 전용 UI 컴포넌트
- `Autodesk.AutoCAD.Ribbon.*` - Ribbon UI (IntelliCAD 버전에 따라 다름)
- `AcadApplication` COM 객체 - IntelliCAD COM 인터페이스 사용 필요

이러한 API를 사용하는 코드는 경고와 함께 대안을 제시합니다.

## Setup Requirements

이 Skill을 사용하기 전에 다음 설정이 필요합니다:

1. Google API Key 설정 (GOOGLE_API_KEY 환경 변수)
2. File Search Store 생성 및 문서 업로드 완료
3. Python 의존성 설치: `pip install google-genai`

```bash
# 초기 설정 (최초 1회)
python .claude/skills/intellicad-api/scripts/setup_store.py --init
```

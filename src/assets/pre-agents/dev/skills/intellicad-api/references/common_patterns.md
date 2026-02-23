# IntelliCAD API 공통 패턴

이 문서는 IntelliCAD ObjectIRX.NET API를 사용할 때 자주 사용되는 코드 패턴을 정리합니다.

## 1. 기본 구조

### 1.1 명령 등록

```csharp
using IntelliCAD.ApplicationServices;
using IntelliCAD.DatabaseServices;
using IntelliCAD.EditorInput;
using IntelliCAD.Runtime;

namespace MyPlugin
{
    public class Commands
    {
        [CommandMethod("MYCOMMAND")]
        public void MyCommand()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Database db = doc.Database;
            Editor ed = doc.Editor;

            // 명령 구현
        }
    }
}
```

### 1.2 트랜잭션 패턴

```csharp
using (Transaction tr = db.TransactionManager.StartTransaction())
{
    try
    {
        // 데이터베이스 작업
        tr.Commit();
    }
    catch (Exception ex)
    {
        ed.WriteMessage($"\n오류: {ex.Message}");
        tr.Abort();
    }
}
```

## 2. 엔티티 생성

### 2.1 ModelSpace에 엔티티 추가

```csharp
BlockTable bt = tr.GetObject(db.BlockTableId, OpenMode.ForRead) as BlockTable;
BlockTableRecord btr = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite) as BlockTableRecord;

// 엔티티 생성
Line line = new Line(new Point3d(0, 0, 0), new Point3d(100, 100, 0));

// ModelSpace에 추가
btr.AppendEntity(line);
tr.AddNewlyCreatedDBObject(line, true);
```

### 2.2 기본 도형 생성

#### Line (선)
```csharp
Line line = new Line(
    new Point3d(0, 0, 0),    // 시작점
    new Point3d(100, 100, 0) // 끝점
);
```

#### Circle (원)
```csharp
Circle circle = new Circle();
circle.Center = new Point3d(50, 50, 0);
circle.Radius = 25;
```

#### Arc (호)
```csharp
Arc arc = new Arc(
    new Point3d(0, 0, 0),  // 중심점
    25,                     // 반지름
    0,                      // 시작 각도 (라디안)
    Math.PI / 2             // 끝 각도 (라디안)
);
```

#### Polyline (폴리라인)
```csharp
Polyline pline = new Polyline();
pline.AddVertexAt(0, new Point2d(0, 0), 0, 0, 0);
pline.AddVertexAt(1, new Point2d(100, 0), 0, 0, 0);
pline.AddVertexAt(2, new Point2d(100, 100), 0, 0, 0);
pline.AddVertexAt(3, new Point2d(0, 100), 0, 0, 0);
pline.Closed = true;
```

## 3. 사용자 입력

### 3.1 점 입력

```csharp
PromptPointOptions ppo = new PromptPointOptions("\n점을 선택하세요: ");
ppo.AllowNone = false;

PromptPointResult ppr = ed.GetPoint(ppo);

if (ppr.Status == PromptStatus.OK)
{
    Point3d point = ppr.Value;
}
```

### 3.2 거리 입력

```csharp
PromptDistanceOptions pdo = new PromptDistanceOptions("\n거리를 입력하세요: ");
pdo.DefaultValue = 10.0;
pdo.AllowNegative = false;

PromptDoubleResult pdr = ed.GetDistance(pdo);

if (pdr.Status == PromptStatus.OK)
{
    double distance = pdr.Value;
}
```

### 3.3 엔티티 선택

```csharp
PromptEntityOptions peo = new PromptEntityOptions("\n객체를 선택하세요: ");
peo.SetRejectMessage("\n유효한 객체를 선택하세요.");
peo.AddAllowedClass(typeof(Line), true);  // Line만 선택 가능

PromptEntityResult per = ed.GetEntity(peo);

if (per.Status == PromptStatus.OK)
{
    ObjectId entityId = per.ObjectId;
    Entity entity = tr.GetObject(entityId, OpenMode.ForRead) as Entity;
}
```

### 3.4 다중 선택

```csharp
PromptSelectionOptions pso = new PromptSelectionOptions();
pso.MessageForAdding = "\n객체들을 선택하세요: ";

// 필터 (Line만 선택)
TypedValue[] filter = new TypedValue[]
{
    new TypedValue((int)DxfCode.Start, "LINE")
};
SelectionFilter sf = new SelectionFilter(filter);

PromptSelectionResult psr = ed.GetSelection(pso, sf);

if (psr.Status == PromptStatus.OK)
{
    SelectionSet ss = psr.Value;
    foreach (SelectedObject so in ss)
    {
        if (so != null)
        {
            Entity entity = tr.GetObject(so.ObjectId, OpenMode.ForRead) as Entity;
        }
    }
}
```

## 4. 속성 설정

### 4.1 색상

```csharp
// 색상 인덱스로 설정 (1=빨강, 2=노랑, 3=녹색, 4=청록, 5=파랑, 6=자홍, 7=흰색)
entity.ColorIndex = 1;

// Color 객체로 설정
entity.Color = Color.FromColorIndex(ColorMethod.ByAci, 1);

// RGB로 설정
entity.Color = Color.FromRgb(255, 0, 0);
```

### 4.2 레이어

```csharp
// 기존 레이어 지정
entity.Layer = "MyLayer";

// 새 레이어 생성
LayerTable lt = tr.GetObject(db.LayerTableId, OpenMode.ForWrite) as LayerTable;

if (!lt.Has("NewLayer"))
{
    LayerTableRecord ltr = new LayerTableRecord();
    ltr.Name = "NewLayer";
    ltr.Color = Color.FromColorIndex(ColorMethod.ByAci, 3);
    lt.Add(ltr);
    tr.AddNewlyCreatedDBObject(ltr, true);
}

entity.Layer = "NewLayer";
```

### 4.3 선 종류 (Linetype)

```csharp
// 선 종류 테이블 확인
LinetypeTable ltt = tr.GetObject(db.LinetypeTableId, OpenMode.ForRead) as LinetypeTable;

if (ltt.Has("DASHED"))
{
    entity.LinetypeId = ltt["DASHED"];
}
```

## 5. 블록 작업

### 5.1 블록 정의 생성

```csharp
BlockTable bt = tr.GetObject(db.BlockTableId, OpenMode.ForWrite) as BlockTable;

// 새 블록 정의
BlockTableRecord newBlock = new BlockTableRecord();
newBlock.Name = "MyBlock";

// 블록에 엔티티 추가
Circle circle = new Circle(Point3d.Origin, Vector3d.ZAxis, 10);
newBlock.AppendEntity(circle);

bt.Add(newBlock);
tr.AddNewlyCreatedDBObject(newBlock, true);
```

### 5.2 블록 참조 삽입

```csharp
BlockTable bt = tr.GetObject(db.BlockTableId, OpenMode.ForRead) as BlockTable;
BlockTableRecord ms = tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite) as BlockTableRecord;

// 블록 참조 생성
BlockReference blockRef = new BlockReference(
    new Point3d(100, 100, 0),  // 삽입점
    bt["MyBlock"]               // 블록 정의 ID
);
blockRef.ScaleFactors = new Scale3d(1.0);  // 스케일
blockRef.Rotation = 0;                      // 회전 (라디안)

ms.AppendEntity(blockRef);
tr.AddNewlyCreatedDBObject(blockRef, true);
```

## 6. 기타 유틸리티

### 6.1 좌표 변환

```csharp
// UCS → WCS 변환
Matrix3d ucsToWcs = ed.CurrentUserCoordinateSystem;
Point3d wcsPoint = ucsPoint.TransformBy(ucsToWcs);

// WCS → UCS 변환
Matrix3d wcsToUcs = ed.CurrentUserCoordinateSystem.Inverse();
Point3d ucsPoint = wcsPoint.TransformBy(wcsToUcs);
```

### 6.2 메시지 출력

```csharp
// 명령줄에 메시지 출력
ed.WriteMessage("\n작업이 완료되었습니다.");
ed.WriteMessage($"\n생성된 객체 수: {count}");
```

### 6.3 객체 삭제

```csharp
Entity entity = tr.GetObject(entityId, OpenMode.ForWrite) as Entity;
entity.Erase();
```

## 7. 예외 처리

```csharp
try
{
    using (Transaction tr = db.TransactionManager.StartTransaction())
    {
        // 작업 수행
        tr.Commit();
    }
}
catch (Autodesk.AutoCAD.Runtime.Exception ex)
{
    // AutoCAD/IntelliCAD 특정 예외
    ed.WriteMessage($"\nCAD 오류: {ex.Message}");
}
catch (System.Exception ex)
{
    // 일반 예외
    ed.WriteMessage($"\n오류: {ex.Message}");
}
```

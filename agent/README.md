# 자율 개발 에이전트팀 (보관용)

사용자가 요구사항을 입력하면 PM → 설계 → 개발 → 테스트 → QA까지
자동으로 수행하는 자율 개발 파이프라인 코드입니다.

## 상태
**보관 중** - 추후 메인 소스에 통합 예정

## 파일 구성

### 핵심 모듈 (src/agent/ 로 이동할 파일들)
- `__init__.py` - 패키지 초기화
- `workflow.py` - WorkflowManager (핵심 파이프라인 엔진)
- `prompts.py` - 단계별 AI 프롬프트 템플릿

### 기존 파일 수정본 (통합 시 참고)
- `commands_with_dev.py` - /dev, /devstatus, /devcancel 명령어 포함 버전
- `callbacks_with_workflow.py` - 워크플로우 취소/상태 콜백 포함 버전
- `keyboards_with_workflow.py` - 워크플로우 제어 키보드 포함 버전
- `main_with_agent.py` - WorkflowManager 초기화 포함 main.py

## 통합 방법
메인 소스에 통합하려면:
1. `workflow.py`, `prompts.py`, `__init__.py` → `src/agent/` 로 복사
2. 나머지 `*_with_*.py` 파일들의 변경사항을 해당 파일에 적용
3. `src/main.py`에 `init_workflow_manager()` 호출 추가

## /dev 명령어 파이프라인

```
/dev <요구사항>
  1/5  🔍 PM 분석      → analysis.md
  2/5  📐 아키텍처 설계 → design.md
  3/5  💻 코드 개발     → src/ 실제 파일 생성
  4/5  🧪 테스트        → test_report.md
  5/5  ✅ QA 검증       → qa_report.md
```

각 단계 결과는 `workspace/<workflow-id>/` 에 저장됩니다.

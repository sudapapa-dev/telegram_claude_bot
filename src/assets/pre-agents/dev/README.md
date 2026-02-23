# 나만의 에이전트 시스템

> 에이전트 시스템 구조를 기반으로 커스터마이징한 개인 개발 에이전트 군단.
> 한국어 지시문 + 영어 코드/기술용어 방식으로 작성.

---

## 시스템 구조

```
오케스트레이터 (나 = Claude)
    │
    ├── builder-*    메타 레벨 — 에이전트/스킬 자체를 만드는 에이전트
    ├── manager-*    방법론 레벨 — 개발 프로세스와 품질을 관리
    ├── expert-*     구현 레벨 — 도메인별 세부 전문가 (221개, 13개 카테고리)
    └── team-*       팀 모드 — 병렬 리서치/설계 (Agent Teams 실험 기능)
```

**총 에이전트: 240개** (builder 3 + manager 8 + expert 221 + team 8)

---

## 에이전트 목록

### Builder 계층 (메타)
| 에이전트 | 역할 |
|---------|------|
| [builder-agent](agents/builder/builder-agent.md) | 새 에이전트 .md 파일 생성 전문가 |
| [builder-skill](agents/builder/builder-skill.md) | 새 스킬 .md 파일 생성 전문가 |
| [builder-plugin](agents/builder/builder-plugin.md) | 새 Claude Code 플러그인 생성 전문가 |

### Manager 계층 (방법론)
| 에이전트 | 역할 |
|---------|------|
| [manager-project](agents/manager/manager-project.md) | 프로젝트 초기화 및 전체 조율 |
| [manager-strategy](agents/manager/manager-strategy.md) | 아키텍처 결정 및 기술 전략 |
| [manager-quality](agents/manager/manager-quality.md) | TRUST 5 품질 게이트 검증 |
| [manager-tdd](agents/manager/manager-tdd.md) | 신규 기능 TDD 구현 |
| [manager-ddd](agents/manager/manager-ddd.md) | 레거시 리팩토링 DDD 구현 |
| [manager-git](agents/manager/manager-git.md) | Git 워크플로우 및 커밋 관리 |
| [manager-spec](agents/manager/manager-spec.md) | SPEC 문서 작성 (EARS 형식) |
| [manager-docs](agents/manager/manager-docs.md) | 기술 문서화, README, API 문서 |

### Expert 계층 (도메인 구현) — 221개, 13개 카테고리

| 카테고리 | 폴더 | 주요 에이전트 | 수 |
|---------|------|------------|---|
| 웹 프론트엔드 | [01-frontend-web](agents/expert/01-frontend-web/) | React, Vue, Angular, Next.js, Svelte, PWA | 17개 |
| UI/CSS/디자인 | [02-frontend-ui-css](agents/expert/02-frontend-ui-css/) | Tailwind, Storybook, Figma, UI Designer, UX Planner | 12개 |
| 모바일/크로스플랫폼 | [03-mobile](agents/expert/03-mobile/) | Flutter, iOS, Electron, Tauri, Kotlin, Swift | 9개 |
| 백엔드 언어 | [04-backend-lang](agents/expert/04-backend-lang/) | Java, Python, Node, Rust, Go, C++, C#, PHP, Ruby 등 | 35개 |
| API/데이터 | [05-backend-api-data](agents/expert/05-backend-api-data/) | GraphQL, PostgreSQL, Redis, MongoDB, Supabase 등 | 25개 |
| DevOps/인프라 | [06-devops-infra](agents/expert/06-devops-infra/) | AWS, K8s, Docker, Terraform, Azure, GCP 등 | 28개 |
| CI/CD & Git | [07-cicd-git](agents/expert/07-cicd-git/) | GitHub Actions, GitLab, Jenkins, Git Flow | 5개 |
| 테스팅/QA | [08-testing-qa](agents/expert/08-testing-qa/) | Playwright, Jest, Cypress, pytest, Vitest | 10개 |
| 코드 품질 | [09-code-quality](agents/expert/09-code-quality/) | 성능, 리팩토링, 기술부채, DX 최적화 | 13개 |
| 보안 | [10-security](agents/expert/10-security/) | 보안 감사, 침투테스트, SRE, 컴플라이언스 | 13개 |
| 아키텍처/리더십 | [11-architecture](agents/expert/11-architecture/) | 아키텍트, PM, CTO, 마이크로서비스 | 15개 |
| 특수 도메인 | [12-special-domain](agents/expert/12-special-domain/) | AI, 게임, 블록체인, IoT, Web3, 핀테크 | 32개 |
| 디버깅/문서 | [13-debugging-docs](agents/expert/13-debugging-docs/) | 디버거, 기술문서, 변경이력 | 7개 |

### Team 계층 (병렬 팀 모드)
> `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 환경변수 필요

| 에이전트 | 역할 |
|---------|------|
| [team-researcher](agents/team/team-researcher.md) | 코드베이스 탐색 및 리서치 |
| [team-analyst](agents/team/team-analyst.md) | 요구사항 분석 및 인수조건 정의 |
| [team-architect](agents/team/team-architect.md) | 기술 아키텍처 설계 |
| [team-designer](agents/team/team-designer.md) | UI/UX 디자인, 컴포넌트 설계 |
| [team-backend-dev](agents/team/team-backend-dev.md) | 백엔드 구현 |
| [team-frontend-dev](agents/team/team-frontend-dev.md) | 프론트엔드 구현 |
| [team-tester](agents/team/team-tester.md) | 테스트 작성 |
| [team-quality](agents/team/team-quality.md) | 품질 검증 |

---

## 핵심 원칙 (My Constitution)

[constitution.md](constitution.md) 참조

---

## 워크플로우

```
/plan → /run → /sync
         ↳ /loop (반복 수정)
         ↳ /fix  (단발 수정)
```

### 스킬 목록
- [auto](skills/workflows/auto.md) — 자율 전체 파이프라인 (plan→run→sync 자동 실행)
- [plan](skills/workflows/plan.md) — SPEC 문서 생성
- [run](skills/workflows/run.md) — SPEC 기반 구현
- [sync](skills/workflows/sync.md) — 문서화 + PR
- [fix](skills/workflows/fix.md) — 단발 수정
- [loop](skills/workflows/loop.md) — 반복 수정 루프
- [feedback](skills/workflows/feedback.md) — 피드백 수집 및 이슈 등록

---

## 배치 방법

### 글로벌 배치 (모든 프로젝트에서 사용)
```bash
# Windows — builder/manager/team (핵심 에이전트)
xcopy /E /I dev\agents\builder %USERPROFILE%\.claude\agents\
xcopy /E /I dev\agents\manager %USERPROFILE%\.claude\agents\
xcopy /E /I dev\agents\team    %USERPROFILE%\.claude\agents\

# expert는 카테고리별 선택 배치 권장
xcopy /E /I dev\agents\expert\01-frontend-web %USERPROFILE%\.claude\agents\
```

### 프로젝트 배치 (이 프로젝트만)
```bash
xcopy /E /I dev\agents .claude\agents\
```

---

## 런타임 데이터 경로

| 데이터 종류 | 경로 |
|------------|------|
| SPEC 문서 | `.sudapapa/specs/SPEC-{ID}/` |
| 보고서 | `.sudapapa/reports/{TYPE}-{DATE}/` |
| 문서 | `.sudapapa/docs/` |
| 체크포인트 | `.sudapapa/memory/checkpoints/` |
| 워크트리 레지스트리 | `.sudapapa/worktrees/` |

---

## TRUST 5 품질 기준

| 기준 | 조건 |
|------|------|
| **T**ested | 테스트 커버리지 85%+ |
| **R**eadable | 순환 복잡도 ≤ 10 |
| **U**nified | 린트 통과, 일관된 스타일 |
| **S**ecured | OWASP Top 10 준수 |
| **T**rackable | Conventional Commits 형식 |

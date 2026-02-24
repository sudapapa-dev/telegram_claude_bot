# telegram_claude_bot

## Project Overview
텔레그램을 통해 Claude Code를 원격 제어하는 시스템.
OAuth 인증 기반으로 Claude Max/Pro 플랜을 그대로 활용할 수 있다.
이름 세션으로 여러 Claude Code 프로세스를 동시에 관리한다.

## Architecture

```
[Telegram Users]
      │
[Telegram Bot (python-telegram-bot)]
      │ MessageQueue (순서 보장)
      │
[Named Session Manager]  ← 이름 세션 라우팅
      │
[Claude Code CLI Processes]  ← OAuth 인증 (~/.claude/.credentials.json)
      │
[SQLite DB (세션/이력 영속화)]
```

### Core Components
1. **Telegram Bot** (`src/telegram/`) - 사용자 인터페이스. 명령 수신, 메시지 큐, 결과 표시
2. **Shared** (`src/shared/`) - 공통 모델, 설정, DB, AI 세션, 이름 세션, 대화 이력

### System Flow
1. 사용자가 텔레그램으로 메시지 전송 (또는 `/new`, `/status` 등 명령)
2. MessageQueue가 순서대로 메시지 처리
3. NamedSessionManager가 이름 세션으로 라우팅 (또는 기본 세션 사용)
4. Claude Code CLI 프로세스가 stream-json 프로토콜로 응답 생성
5. 결과를 텔레그램으로 전달 (3000자 초과 시 파일 전송)

## Tech Stack
- **Language**: Python 3.11+
- **Telegram**: python-telegram-bot v21+
- **Database**: SQLite (aiosqlite)
- **Process Management**: asyncio.subprocess for Claude Code CLI
- **Config**: Pydantic Settings (.env) + claude CLI 경로 자동 탐지
- **Logging**: structlog
- **EXE Build**: PyInstaller (단일 파일)

## Project Structure
```
telegram_claude_bot/
├── CLAUDE.md
├── .claude/agents/              # 에이전트 팀 정의
├── src/                         # 모든 소스 코드는 src/ 안에만
│   ├── __init__.py
│   ├── main.py                  # 진입점 (봇 부트스트랩 + exe entry)
│   ├── telegram/
│   │   ├── bot.py               # Bot + MessageQueue 초기화 및 실행
│   │   └── handlers/
│   │       └── commands.py      # /start, /new, /open, /close, /status 등
│   └── shared/
│       ├── config.py            # Pydantic Settings + claude 경로 자동 탐지
│       ├── models.py            # 데이터 모델 (ChatMessage, NamedSession)
│       ├── database.py          # SQLite (chat_history, named_sessions)
│       ├── ai_session.py        # Claude CLI 세션 관리 (stream-json)
│       ├── named_sessions.py    # 이름 세션 관리자
│       └── chat_history.py      # 대화 이력 저장소
├── tests/
├── .env.example
├── pyproject.toml
└── deploy/
    ├── docker/                  # Docker/NAS 배포
    └── windows/                 # Windows 배포 (install.bat, NSSM 서비스, PyInstaller)
```

## Telegram Commands
- `/start` - 봇 시작 및 도움말
- `/new [이름]` - 새 대화 시작 또는 이름 세션 생성
- `/open <이름> [디렉토리]` - 이름 세션 생성 (디렉토리 선택적)
- `/close [이름]` - 세션 종료 (이름 생략 시 기본 세션 초기화)
- `/default [이름]` - 기본 라우팅 세션 설정/해제
- `/job` - 처리 중/대기 중 작업 목록
- `/clean` - 대화 이력 및 캐시 초기화
- `/status` - 시스템 상태
- `/history` - 대화 이력
- `@` - 세션 목록 조회
- `@세션이름 메시지` - 특정 세션에 메시지 전달

## Authentication
- Claude Code는 OAuth 브라우저 인증 사용 (`claude login`)
- 인증 파일: `~/.claude/.credentials.json` (이것 하나만 필요)
- Docker 환경: `claude_auth/` 볼륨 마운트 → `docker restart`로 반영
- Windows 서비스: `config.py`가 claude CLI 절대 경로를 자동 탐지

## Build & Run

### 개발 실행
```bash
pip install -e .
python -m src.main
```

### EXE 빌드
```bash
pip install pyinstaller
pyinstaller deploy/windows/telegram_claude_bot.spec --clean --noconfirm --workpath build/.tmp --distpath dist
# dist/telegram_claude_bot/ 폴더 생성됨
# install.bat 실행 → 환경 설치 → telegram_claude_bot.exe 실행
```

## Coding Conventions
- Type hints 필수 (Python 3.11+ style)
- async/await 패턴 우선
- Pydantic v2 모델 사용
- docstring은 한국어로 작성
- 변수/함수/클래스명은 영어
- 로깅: structlog 사용
- 모든 소스 코드는 `src/` 폴더 안에만 위치

## Agent Team

### General Rules
1. 이 CLAUDE.md를 단일 진실 소스로 참조
2. 자신의 담당 디렉토리만 수정
3. `src/shared/` 변경 시 다른 에이전트에 영향 고지
4. 모든 공개 함수에 type hints 필수

### Inter-agent Communication
- 공유 인터페이스: `src/shared/models.py`
- 이름 세션 관리: `src/shared/named_sessions.py` NamedSessionManager

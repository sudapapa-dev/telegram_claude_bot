# telegram_claude_bot

## Project Overview
Claude Code Orchestration System - 텔레그램을 통해 다수의 Claude Code 인스턴스를 원격 제어하고 모니터링하는 시스템.
사용자별 Anthropic API 키를 관리하여 각자의 모델/요금제로 Claude Code를 사용할 수 있다.

## Architecture

```
[Telegram Users]
      │
[Telegram Bot (python-telegram-bot)]
      │
[Orchestrator (InstanceManager + TaskQueue)]
      │
[Claude Code CLI Processes]  ← 인스턴스별 ANTHROPIC_API_KEY 환경변수 주입
      │
[SQLite DB (상태 영속화)]
```

### Core Components
1. **Telegram Bot** (`src/telegram/`) - 사용자 인터페이스. 명령 수신, 결과 표시, 모니터링 UI
2. **Orchestrator** (`src/orchestrator/`) - 핵심 엔진. Claude Code 프로세스 생명주기 관리 및 작업 실행
3. **Shared** (`src/shared/`) - 공통 모델, 설정, DB, 이벤트 버스

### System Flow
1. 사용자가 텔레그램으로 명령 전송 (`/run`, `/status` 등)
2. 텔레그램 봇 핸들러가 Orchestrator를 직접 호출
3. Orchestrator가 Claude Code CLI 프로세스를 spawn (인스턴스별 API 키/모델 적용)
4. 결과를 Orchestrator → 텔레그램 봇 → 사용자에게 전달
5. 비동기 작업은 EventBus를 통해 완료 알림 push

## Tech Stack
- **Language**: Python 3.11+
- **Telegram**: python-telegram-bot v21+
- **Database**: SQLite (aiosqlite)
- **Process Management**: asyncio.subprocess for Claude Code CLI
- **Config**: Pydantic Settings (.env)
- **Logging**: structlog
- **EXE Build**: PyInstaller (단일 파일)

## Project Structure
```
telegram_claude_bot/
├── CLAUDE.md
├── .claude/agents/              # 에이전트 팀 정의
├── src/                         # 모든 소스 코드는 src/ 안에만
│   ├── __init__.py
│   ├── main.py                  # 진입점 (봇 + 오케스트레이터 부트스트랩 + exe entry)
│   ├── telegram/
│   │   ├── bot.py               # Bot 초기화 및 실행
│   │   ├── handlers/
│   │   │   ├── commands.py      # /start, /status, /run, /setkey, /settoken 등
│   │   │   └── callbacks.py     # Inline keyboard + ConversationHandler
│   │   └── keyboards.py         # Inline keyboard 빌더
│   ├── orchestrator/
│   │   ├── manager.py           # 인스턴스 매니저
│   │   ├── process.py           # Claude Code CLI 프로세스 래퍼
│   │   └── queue.py             # 우선순위 작업 큐
│   └── shared/
│       ├── config.py            # Pydantic Settings
│       ├── models.py            # 데이터 모델
│       ├── database.py          # SQLite
│       └── events.py            # 이벤트 버스
├── tests/
├── .env.example
├── pyproject.toml
└── deploy/windows/telegram_claude_bot.spec  # PyInstaller exe 빌드
```

## Telegram Commands
- `/start` - 봇 시작 및 도움말
- `/status` - 전체 시스템 상태 요약
- `/instances` - 인스턴스 목록 (인라인 키보드)
- `/create <name> <dir> <api_key> [model]` - 인스턴스 생성
- `/run <id> <prompt>` - 작업 실행
- `/logs <id>` - 로그 조회
- `/stop <id>` / `/stopall` - 중지
- `/setkey <id> <key>` - API 키 변경
- `/setmodel <id> <model>` - 모델 변경
- `/settoken <token>` - 봇 토큰 변경 (.env 업데이트, 재시작 필요)

## Build & Run

### 개발 실행
```bash
pip install -e .
python -m src.main
```

### EXE 빌드
```bash
pip install pyinstaller
pyinstaller deploy/windows/telegram_claude_bot.spec --clean --noconfirm --workpath build/.tmp --distpath build
# build/telegram_claude_bot/ 폴더 생성됨 → 같은 폴더에 .env 파일 필요
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
- 이벤트 기반: `src/shared/events.py` EventBus
- 텔레그램 봇은 Orchestrator InstanceManager를 직접 의존성 주입

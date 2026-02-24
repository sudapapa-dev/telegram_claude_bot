# telegram_claude_bot

텔레그램을 통해 Claude Code를 원격 제어하는 시스템.
메시지를 보내면 Claude가 응답하며, 이름 세션으로 여러 Claude 인스턴스를 동시에 관리할 수 있습니다.

![텔레그램 명령][images/shot.png]
![실제 노션 화면][images/shot2.png]

---

## 목차

- [주요 기능](#주요-기능)
- [사전 준비](#사전-준비)
- [Windows 바로 실행](#windows-바로-실행)
  - [Windows 서비스 등록 (선택)](#windows-서비스-등록-선택)
- [Windows 개발 및 빌드](#windows-개발-및-빌드)
  - [소스에서 직접 실행](#소스에서-직접-실행)
  - [EXE 빌드](#exe-빌드)
- [Linux / Docker 설치 및 실행](#linux--docker-설치-및-실행)
  - [방법 1: Docker Compose (권장)](#방법-1-docker-compose-권장)
  - [방법 2: 직접 실행](#방법-2-직접-실행)
  - [Claude CLI 인증 (Linux/Docker)](#claude-cli-인증-linuxdocker)
- [Notion MCP 설정](#notion-mcp-설정)
- [.env 설정](#env-설정)
- [텔레그램 명령어](#텔레그램-명령어)
- [이름 세션 시스템](#이름-세션-시스템)
- [아키텍처](#아키텍처)
- [문제 해결](#문제-해결)

---

## 주요 기능

- **대화형 Claude** - 텔레그램 메시지로 Claude Code CLI와 직접 대화
- **이름 세션** - `@세션이름 메시지` 형식으로 여러 Claude 인스턴스를 동시 운영
- **기본 세션** - `/default` 명령으로 이름 없는 메시지를 특정 세션에 자동 라우팅
- **이미지 분석** - 사진을 전송하면 Claude가 이미지를 분석
- **메시지 큐** - 동시 메시지를 순서대로 처리, `/job`으로 대기열 확인
- **대화 이력** - DB 기반 대화 이력 저장 및 조회
- **시스템 프롬프트** - `.env`에서 다중 시스템 프롬프트 설정 지원
- **자동 재시작** - DEAD 세션 자동 감지 및 재시작 (알림 포함)
- **다중 배포** - Windows (EXE / 서비스), Linux (Docker / 직접 실행) 지원

---

## 사전 준비

플랫폼에 관계없이 아래 두 가지가 필요합니다.

### 1. 텔레그램 봇 토큰 발급

1. 텔레그램에서 **@BotFather** 검색 → `/newbot` 명령
2. 봇 이름과 사용자명(`_bot`으로 끝나야 함) 입력
3. 발급된 토큰을 메모 (형식: `1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ`)

### 2. 내 Chat ID 확인

텔레그램에서 **@userinfobot** 에게 아무 메시지를 보내면 Chat ID를 알려줍니다.

---

## Windows 바로 실행

1. `exe/telegram_claude_bot.zip`을 원하는 곳에 압축 해제
2. `install.bat` 더블클릭 — Node.js, Claude CLI, .env 등 필수 환경 자동 설치
3. `telegram_claude_bot.exe` 직접 실행

> 처음 실행 시 별도 터미널에서 `claude login`으로 Claude CLI 인증이 필요합니다.

### Windows 서비스 등록 (선택)

서비스로 등록하면 봇이 비정상 종료되었을 때 자동으로 재시작됩니다.

```cmd
:: 서비스 등록 (관리자 권한 자동 요청, Windows 비밀번호 입력 필요)
install_service.bat

:: 서비스 제거
remove_service.bat
```

- 현재 사용자 계정으로 실행 (Claude CLI 인증 자동 적용)
- 부팅 시 자동 시작
- 오류 발생 시 60초 후 자동 재시작
- 로그: `logs/` 폴더에 stdout/stderr 기록

> NSSM이 없으면 winget 또는 choco로 자동 설치를 시도합니다.

---

## Windows 개발 및 빌드

### 소스에서 직접 실행

```cmd
:: 필수: Python 3.11+, Node.js, Claude CLI
pip install -e .
copy .env.example .env
:: .env 편집: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 입력
claude login
python -m src.main
```

### EXE 빌드

```cmd
pip install pyinstaller
pyinstaller deploy/windows/telegram_claude_bot.spec --clean --noconfirm --workpath build/.tmp --distpath dist
```

빌드 결과:

```
dist/telegram_claude_bot/
  telegram_claude_bot.exe     ← 실행 파일
  _internal/                  ← 런타임 의존성
  install.bat                 ← 환경 설치 스크립트
  install_service.bat         ← NSSM 서비스 등록
  remove_service.bat          ← NSSM 서비스 제거
  .env.example                ← 설정 파일 템플릿
  scripts/                    ← 스크립트 디렉토리
```

---

## Linux / Docker 설치 및 실행

### 방법 1: Docker Compose (권장)

Docker 이미지에 Python, Node.js, Claude Code CLI, Notion MCP가 모두 포함됩니다.

```bash
cd deploy/docker

# 환경 설정
cp .env.example .env
# .env 편집: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 입력

# 빌드 및 실행
docker compose up -d --build
```

#### 디렉토리 구조

```
deploy/docker/
├── .env               ← 봇 설정 (직접 생성)
├── data/              ← DB, 대화 이력 (자동 생성)
├── workspace/         ← Claude 작업 디렉토리 (자동 생성)
├── sessions/          ← 세션별 작업 디렉토리 (자동 생성)
└── claude_auth/       ← Claude CLI 인증 파일 (수동 복사 또는 docker exec로 생성)
```

#### 주요 볼륨 마운트

| 호스트 경로 | 컨테이너 경로 | 용도 |
|-------------|---------------|------|
| `./data` | `/app/data` | DB, 대화 이력 영속화 |
| `./workspace` | `/app/workspace` | Claude 작업 디렉토리 |
| `./sessions` | `/app/sessions` | 세션별 작업 디렉토리 |
| `./claude_auth` | `/home/appuser/.claude` | Claude CLI 인증 파일 |
| `./.env` | `/app/.env` (읽기 전용) | 봇 설정 |

> `.env` 수정 후 `docker restart telegram_claude_bot`으로 반영됩니다.

### 방법 2: 직접 실행

```bash
# 필수 소프트웨어 설치
# Python 3.11+, Node.js, Claude CLI 필요
npm install -g @anthropic-ai/claude-code

# 패키지 설치
pip install -e .

# 환경 설정
cp .env.example .env
# .env 편집

# Claude CLI 인증
claude login

# 실행
python -m src.main
```

### Claude CLI 인증 (Linux/Docker)

Claude Code CLI는 OAuth 브라우저 인증을 사용합니다.
GUI 브라우저가 없는 Linux/Docker/NAS 환경에서는 아래 방법으로 인증합니다.

#### 방법 A: 로컬 PC에서 인증 파일 복사 (권장)

GUI 브라우저가 있는 PC에서 인증하고, 인증 파일(`~/.claude/.credentials.json`)을 서버로 복사합니다.

```bash
# 1. 로컬 PC에서 인증
claude login

# 2. 인증 파일을 서버로 복사
scp ~/.claude/.credentials.json user@SERVER:/path/to/deploy/docker/claude_auth/

# 3. 컨테이너 재시작
docker restart telegram_claude_bot
```

Windows에서 NAS로 복사하는 경우:

```powershell
copy "$env:USERPROFILE\.claude\.credentials.json" "\\NAS_IP\path\to\claude_auth\"
```

#### 방법 B: 컨테이너 내부에서 직접 인증

```bash
docker exec -it telegram_claude_bot claude login
# 출력되는 URL을 브라우저에서 열어 인증
```

> OAuth 콜백이 localhost로 돌아오므로, **같은 머신의 브라우저**에서 URL을 열어야 합니다.

#### 토큰 만료 시 재인증

OAuth 토큰은 일정 기간 후 만료됩니다. 봇에서 `401 authentication_error` 오류가 발생하면 위 방법 A 또는 B를 다시 수행하고 컨테이너를 재시작합니다.

```bash
docker restart telegram_claude_bot
```

#### 인증 파일 구조

```
claude_auth/                          ← docker-compose 볼륨 마운트
├── .credentials.json                 ← OAuth 토큰 (accessToken, refreshToken) ★ 필수
├── settings.json                     ← CLI 설정 (선택)
└── ...                               ← 기타 캐시/이력 파일
```

> 인증에 필요한 파일은 `~/.claude/.credentials.json` 하나뿐입니다.

---

## Notion MCP 설정

`.env`에 `NOTION_TOKEN`을 설정하면 봇 시작 시 자동으로 Claude CLI에 Notion MCP가 연결됩니다. 별도의 MCP 수동 설정은 필요 없습니다.

```
.env (NOTION_TOKEN) → ~/.claude.json (자동 주입) → Claude CLI → Notion API
```

### 1단계: Internal Integration 생성

1. [Notion Integrations 페이지](https://www.notion.so/profile/integrations) 접속
2. **"새 API 통합 만들기"** 클릭
3. 이름 입력 (예: `telegram_bot`), 워크스페이스 선택, 유형: Internal
4. **저장** 클릭

### 2단계: 토큰을 .env에 설정

생성된 Integration에서 **"내부 통합 시크릿"** 을 복사하여 `.env`에 설정합니다.

```env
NOTION_TOKEN=ntn_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3단계: 페이지 권한 부여

Integration을 만들었더라도, **접근할 페이지에 직접 연결해야** API로 접근이 가능합니다.

- [Notion Integrations 페이지](https://www.notion.so/profile/integrations)에서 만든 Integration 클릭
- **"콘텐츠 사용 권한"** 탭 → **"편집 권한"** → 접근할 최상위 페이지 체크 → **"저장하기"**
- 최상위 페이지를 선택하면 하위 페이지 전체에 자동 적용됩니다

### 4단계: 봇 재시작

시작 로그에 `Notion MCP 설정 주입 완료` 메시지가 나타나면 정상입니다.

### 사용 예시

텔레그램에서 Claude에게 직접 요청합니다:

- `"노션에 오늘 회의록 페이지를 만들어줘"`
- `"노션에서 '프로젝트 계획' 페이지 내용을 요약해줘"`
- `"노션 데이터베이스에 새 항목을 추가해줘"`

### Notion MCP 제한사항

| 항목 | 내용 |
|------|------|
| 페이지 접근 | Integration이 연결된 페이지만 접근 가능 |
| 새 최상위 페이지 | 새로 만든 최상위 페이지는 별도로 Integration 연결 필요 |
| 요청 제한 | 초당 3회 (Rate Limit) |
| 파일 업로드 | API로 직접 파일 업로드 불가 (External URL만 지원) |

---

## .env 설정

```env
# 필수
TELEGRAM_BOT_TOKEN=your-telegram-bot-token

# 접근 제한 (강력 권장 - 미설정 시 누구나 접근 가능)
TELEGRAM_CHAT_ID=[123456789]

# Claude
CLAUDE_CODE_PATH=claude
# DEFAULT_MODEL=claude-sonnet-4-6
DEFAULT_SESSION_NAME=suho

# 선택
NOTION_TOKEN=

# 시스템 프롬프트 (단일 또는 다중)
SYSTEM_PROMPT_1=You are a Task Manager.
SYSTEM_PROMPT_2=Always respond in Korean.
```

| 변수 | 필수 | 설명 |
|------|------|------|
| `TELEGRAM_BOT_TOKEN` | ✅ | @BotFather에서 발급받은 봇 토큰 |
| `TELEGRAM_CHAT_ID` | ⚠️ | 허용된 텔레그램 Chat ID 목록 (JSON 배열). 미설정 시 모든 사용자 접근 가능 |
| `CLAUDE_CODE_PATH` | - | Claude Code CLI 경로 (기본: `claude`, PATH/공통 경로 자동 탐지) |
| `DEFAULT_MODEL` | - | Claude 모델 지정 (미설정 시 CLI 기본 모델 사용) |
| `DEFAULT_SESSION_NAME` | - | 봇 시작 시 자동 생성되는 기본 세션 이름 (기본: `suho`) |
| `NOTION_TOKEN` | - | Notion MCP 연동 토큰 (설정 시 `~/.claude.json`에 자동 주입) |
| `SYSTEM_PROMPT` | - | 사전 시스템 프롬프트 (단일) |
| `SYSTEM_PROMPT_1~N` | - | 다중 시스템 프롬프트 (번호순 합침, 단일과 동시 사용 가능) |

> **보안**: `TELEGRAM_CHAT_ID`를 반드시 설정하세요. 미설정 시 누구나 봇에 접근할 수 있습니다.

---

## 텔레그램 명령어

### 대화 및 세션

| 명령어 | 설명 |
|--------|------|
| `/start`, `/help` | 봇 시작 및 도움말 표시 |
| `/new [이름]` | 새 대화 시작. 이름 지정 시 이름 세션 생성 (자동 디렉토리) |
| `/open <이름> [디렉토리]` | 이름 세션 생성 (디렉토리 선택적) |
| `/close [이름]` | 세션 종료. 이름 생략 시 기본 세션 초기화 |
| `/default [이름]` | 기본 라우팅 세션 설정/해제. 인수 없으면 .env 기본값 복원 |
| `@` | 세션 목록 조회 |
| `@세션이름 메시지` | 특정 세션에 메시지 전달 |

### 시스템 관리

| 명령어 | 설명 |
|--------|------|
| `/status` | 전체 시스템 상태 (세션 수, 상태별 현황, 기본 세션) |
| `/job` | 처리 중/대기 중 작업 목록 |
| `/history [n]` | 최근 대화 이력 조회 (기본 10개) |
| `/history db [n]` | DB 저장 이력 조회 |
| `/clean` | 대화 이력 및 세션 캐시 전체 초기화 |

---

## 이름 세션 시스템

이름 세션은 독립적인 Claude Code 프로세스로, 각각 고유한 작업 디렉토리와 대화 컨텍스트를 유지합니다.

```
/new 데이빗                    # 자동 디렉토리로 세션 생성
/open 앨리스 C:/projects/web   # 지정 디렉토리로 세션 생성
@데이빗 리포트 작성해줘         # 데이빗 세션에 메시지 전달
/default 데이빗                # 이름 없는 메시지를 데이빗으로 라우팅
/close 데이빗                  # 세션 종료
```

### 세션 상태

| 상태 | 아이콘 | 설명 |
|------|--------|------|
| `idle` | 🟢 | 대기 중 |
| `busy` | 🟡 | 작업 처리 중 |
| `dead` | 🔴 | 프로세스 종료됨 (자동 재시작) |

---

## 아키텍처

```
[Telegram Users]
      │
[Telegram Bot (python-telegram-bot v21+)]
      │ MessageQueue (순서 보장)
      │
[Named Session Manager]  ← 이름 세션 라우팅
      │
[Claude Code CLI Processes]  ← stream-json 프로토콜
      │
[SQLite DB (세션/이력 영속화)]
```

### 핵심 컴포넌트
1. **Telegram Bot** (`src/telegram/`) - 사용자 인터페이스, 메시지 큐
2. **Shared** (`src/shared/`) - 설정, 모델, DB, AI 세션, 이름 세션, 대화 이력

### 프로젝트 구조
```
telegram_claude_bot/
├── src/
│   ├── main.py                  # 진입점
│   ├── telegram/
│   │   ├── bot.py               # Bot + MessageQueue
│   │   └── handlers/
│   │       └── commands.py      # 명령 핸들러
│   └── shared/
│       ├── config.py            # Pydantic Settings + claude 경로 자동 탐지
│       ├── models.py            # 데이터 모델
│       ├── database.py          # SQLite
│       ├── ai_session.py        # Claude CLI 세션 관리
│       ├── named_sessions.py    # 이름 세션 관리자
│       └── chat_history.py      # 대화 이력 저장소
├── deploy/
│   ├── docker/                  # Dockerfile, docker-compose.yml
│   └── windows/                 # install.bat, EXE 빌드, NSSM 서비스
├── tests/
├── .env.example
└── pyproject.toml
```

### 기술 스택

- **Python** 3.11+ (async/await, type hints)
- **python-telegram-bot** v21+
- **Pydantic** v2 + pydantic-settings
- **SQLite** (aiosqlite)
- **structlog** (로깅)
- **Claude Code CLI** (stream-json 프로토콜)
- **PyInstaller** (Windows EXE 빌드)
- **Docker** (Linux/NAS 배포)

---

## 문제 해결

### Windows

| 증상 | 해결 방법 |
|------|----------|
| "python을 찾을 수 없습니다" | Python 설치 후 터미널 재시작. "Add Python to PATH" 체크 확인 |
| "claude를 찾을 수 없습니다" | Node.js 설치 후 터미널 재시작. PATH 갱신 필요 |
| `[WinError 2]` (서비스 환경) | `.env`에 절대 경로 설정: `CLAUDE_CODE_PATH=C:\Users\사용자명\.local\bin\claude.exe` |
| 봇이 응답하지 않음 | `.env`의 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 값 확인. `claude login` 인증 확인 |

### Linux / Docker

| 증상 | 해결 방법 |
|------|----------|
| `401 authentication_error` | OAuth 토큰 만료. `claude login` 재인증 후 `.credentials.json` 재복사, 컨테이너 재시작 |
| 컨테이너 즉시 종료 | `docker logs telegram_claude_bot`으로 오류 확인. `.env` 설정 누락 여부 확인 |
| 인증 URL 접근 불가 | OAuth 콜백은 localhost로 돌아옴. 같은 머신의 브라우저에서 열거나, 방법 A(파일 복사) 사용 |
| 권한 오류 | `claude_auth/`, `data/`, `workspace/` 디렉토리 권한 확인 (`chmod 755`) |

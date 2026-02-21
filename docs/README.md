# Claude Control Tower - 상세 문서

> 텔레그램 봇을 통해 AI(Claude / Gemini)를 원격 제어하는 자동화 시스템

---

## 목차

1. [개요](#개요)
2. [시스템 아키텍처](#시스템-아키텍처)
3. [디렉토리 구조](#디렉토리-구조)
4. [핵심 컴포넌트](#핵심-컴포넌트)
5. [AI Provider](#ai-provider)
6. [텔레그램 봇 명령어](#텔레그램-봇-명령어)
7. [설정 (환경변수)](#설정-환경변수)
8. [Docker 배포 (NAS)](#docker-배포-nas)
9. [인증 관리](#인증-관리)
10. [데이터 흐름](#데이터-흐름)
11. [트러블슈팅](#트러블슈팅)

---

## 개요

**Claude Control Tower**는 텔레그램 봇을 인터페이스로 사용하여 AI CLI(Claude Code, Gemini CLI)를 원격으로 제어하는 시스템입니다.

### 주요 특징

| 특징 | 설명 |
|------|------|
| 🤖 다중 AI 지원 | Claude Code, Gemini CLI 전환 가능 |
| 📱 텔레그램 인터페이스 | 모바일/PC 어디서나 명령 전송 |
| 🐳 Docker 지원 | 시놀로지 NAS에서 컨테이너로 운영 |
| 🔐 OAuth 인증 | API Key 없이 로그인 방식 사용 |
| 📋 대화 이력 | DB + JSON 기반 대화 기록 저장 |
| ⚡ 병렬 처리 | 최대 5개 메시지 동시 처리 큐 |

### 운영 환경

- **NAS**: 시놀로지 DS923+ (`172.16.42.98`)
- **컨테이너**: `controltower-sudapapalinux`
- **텔레그램 봇**: `@sudapapalinux_bot`
- **이미지**: `claude-controltower:latest` (1.74GB)

---

## 시스템 아키텍처

```
[사용자 - 텔레그램 앱]
        ↓ 메시지 전송
[텔레그램 봇 서버]
        ↓ polling
[ControlTowerBot] ← python-telegram-bot
        ↓
[MessageQueue] → 최대 5개 병렬 처리
        ↓
[AISessionManager] ← 현재 선택된 AI Provider
        ↓
    ┌──────────────────────┐
    │  ClaudeSession       │  ← stream-json 프로토콜
    │  GeminiSession       │  ← subprocess 요청별 실행
    └──────────────────────┘
        ↓
[ChatHistoryStore] → DB + JSON 저장
```

---

## 디렉토리 구조

```
D:\claude_controltower\
├── src/                          # 소스코드
│   ├── main.py                   # 진입점
│   ├── shared/
│   │   ├── ai_session.py         # AI Provider 추상화 (핵심)
│   │   ├── claude_session.py     # (레거시 - ai_session으로 통합)
│   │   ├── config.py             # 환경변수 설정
│   │   ├── database.py           # SQLite DB (aiosqlite)
│   │   ├── chat_history.py       # 대화 이력 관리
│   │   ├── events.py             # 이벤트 버스
│   │   └── models.py             # 데이터 모델
│   ├── orchestrator/
│   │   ├── manager.py            # 인스턴스 관리자
│   │   ├── process.py            # 프로세스 관리
│   │   └── queue.py              # 작업 큐
│   └── telegram/
│       ├── bot.py                # 봇 메인 + MessageQueue
│       ├── keyboards.py          # 인라인 키보드
│       └── handlers/
│           ├── commands.py       # /명령어 핸들러
│           └── callbacks.py      # 버튼 콜백 핸들러
├── docs/                         # 문서
│   └── README.md                 # 이 문서
├── scripts/                      # 유틸리티 스크립트
│   ├── screenshot.py             # 스크린샷
│   ├── launch_program.py         # 프로그램 실행
│   └── find_process.py           # 프로세스 탐색
├── Dockerfile                    # Docker 이미지 빌드
├── docker-compose.yml            # 컨테이너 구성
├── pyproject.toml                # Python 패키지 설정
└── .env                          # 환경변수 (gitignore)
```

---

## 핵심 컴포넌트

### 1. `src/main.py` - 진입점

시스템 전체를 초기화하고 실행합니다.

```python
async def _async_main():
    settings = Settings()          # .env 로드
    db = Database(...)             # SQLite 초기화
    ai_session.init_default(...)   # AI 세션 매니저 초기화
    history_store = ChatHistoryStore(...)  # 대화 이력
    orchestrator = InstanceManager(...)    # 인스턴스 관리자
    bot = ControlTowerBot(...)     # 텔레그램 봇 시작
```

### 2. `src/shared/ai_session.py` - AI Provider 추상화

가장 핵심적인 모듈. Claude와 Gemini를 동일 인터페이스로 관리합니다.

**AIProvider Enum**
```python
class AIProvider(str, Enum):
    CLAUDE = "claude"   # 🟣 Claude Code CLI
    GEMINI = "gemini"   # 🔵 Gemini CLI
```

**ClaudeSession** - `stream-json` 프로토콜로 장기 프로세스 유지
```
claude -p --dangerously-skip-permissions --input-format stream-json ...
```
- 프로세스를 계속 살려두고 stdin/stdout으로 대화
- JSON 스트리밍 방식으로 응답 수집

**GeminiSession** - 요청별 subprocess 실행
```
gemini -p "<prompt>"
```
- 매 요청마다 새 프로세스 실행
- `~/.gemini/oauth_creds.json`으로 자동 인증

**AISessionManager** - 전역 세션 관리
```python
mgr = get_manager()
await mgr.new_session(AIProvider.GEMINI)  # AI 전환
reply = await mgr.ask("안녕하세요")        # 질의
```

### 3. `src/telegram/bot.py` - 봇 & MessageQueue

```
메시지 수신 → "⏳ 처리 중..." 즉시 응답 → 큐에 추가
                                              ↓
                                    worker(최대 5개 병렬)
                                              ↓
                                    AI 처리 → 응답 전송
```

**MessageQueue** 특징:
- 최대 5개 동시 처리 (`MAX_WORKERS = 5`)
- 큐 대기 시 "앞에 N개" 표시
- 3000자 초과 응답은 `.md` 파일로 전송

### 4. `src/telegram/handlers/commands.py` - 명령어 처리

모든 텔레그램 `/명령어`를 처리합니다.

### 5. `src/shared/database.py` - SQLite DB

`aiosqlite` 기반 비동기 DB. 인스턴스와 작업 이력을 저장합니다.

---

## AI Provider

### 🟣 Claude Code CLI

| 항목 | 내용 |
|------|------|
| 인증 방식 | Claude OAuth (`~/.claude/.credentials.json`) |
| 실행 방식 | 장기 프로세스 유지 (stream-json) |
| 모델 | `claude-sonnet-4-6` (기본) |
| 특징 | Bash/파일 조작 도구 사용 가능, PC 제어 가능 |

### 🔵 Gemini CLI

| 항목 | 내용 |
|------|------|
| 인증 방식 | Google OAuth (`~/.gemini/oauth_creds.json`) |
| 실행 방식 | 요청별 subprocess (`gemini -p "..."`) |
| 모델 | `gemini-2.0-flash` (기본) |
| 특징 | 무료 (개인 Google 계정), API Key 불필요 |

---

## 텔레그램 봇 명령어

| 명령어 | 설명 |
|--------|------|
| `/start` | 도움말 표시 |
| `/help` | 도움말 표시 |
| `/new` | **새 대화 시작 + AI 선택** (Claude/Gemini 인라인 버튼) |
| `/status` | 인스턴스 상태 조회 |
| `/logs <id> [n]` | 인스턴스 로그 조회 (기본 30줄) |
| `/setmodel <id> <model>` | 인스턴스 모델 변경 |
| `/history [n]` | 최근 대화 이력 조회 |
| `일반 메시지` | AI에게 직접 전달 |
| `이미지 전송` | 이미지 + 캡션을 AI에 전달 |

### /new 명령어 동작 흐름

```
/new 입력
    ↓
[🆕 새 대화 시작]
현재: 🟣 Claude Code

[✅ 🟣 Claude Code]  ← 현재 선택 표시
[🔵 Gemini CLI]
[❌ 취소]
    ↓ 버튼 선택
[✅ AI 전환 완료]
🟣 Claude Code → 🔵 Gemini CLI
새 대화가 시작됩니다. 메시지를 입력하세요!
```

---

## 설정 (환경변수)

`.env` 파일 또는 Docker `-e` 옵션으로 설정합니다.

```env
# 텔레그램 (필수)
TELEGRAM_BOT_TOKEN=<봇 토큰>
TELEGRAM_CHAT_ID=[<허용할 유저 ID>]
ALLOWED_USERS=3                     # 최대 동시 인스턴스 수

# Claude
CLAUDE_CODE_PATH=claude             # Claude CLI 경로
DEFAULT_MODEL=claude-sonnet-4-6    # 기본 모델
CLAUDE_WORKSPACE=/app/workspace    # 작업 디렉토리

# Gemini
GEMINI_PATH=gemini                 # Gemini CLI 경로
GEMINI_MODEL=gemini-2.0-flash     # Gemini 모델

# DB
DATABASE_PATH=/app/data/controltower.db
```

---

## Docker 배포 (NAS)

### 이미지 빌드

```bash
# NAS SSH 접속 후
cd /var/services/homes/b17314/.dockerimages/controltower
sudo docker build -t claude-controltower:latest .
```

### 컨테이너 실행

```bash
sudo docker run -d \
  --name controltower-sudapapalinux \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN=<토큰> \
  -e TELEGRAM_CHAT_ID=[<유저ID>] \
  -e CLAUDE_CODE_PATH=claude \
  -e DEFAULT_MODEL=claude-sonnet-4-6 \
  -e GEMINI_PATH=gemini \
  -e GEMINI_MODEL=gemini-2.0-flash \
  -v /path/to/data:/app/data \
  -v /path/to/workspace:/app/workspace \
  -v /path/to/.claude:/home/appuser/.claude \
  -v /path/to/.gemini:/home/appuser/.gemini \
  claude-controltower:latest
```

### 볼륨 구조 (NAS)

```
/var/services/homes/b17314/.dockerimages/claude_controltower/
├── data_sudapapalinux/          → /app/data (DB 저장)
├── workspace_sudapapalinux/     → /app/workspace (작업 공간)
├── .claude_sudapapalinux/       → /home/appuser/.claude (Claude 인증)
│   └── .credentials.json
└── .gemini_sudapapalinux/       → /home/appuser/.gemini (Gemini 인증)
    ├── oauth_creds.json
    └── google_accounts.json
```

---

## 인증 관리

### Claude 인증

Claude CLI는 OAuth 방식으로 `~/.claude/.credentials.json`에 토큰을 저장합니다.

**인증 갱신 방법:**
```bash
# 컨테이너 내부에서
claude auth login
# URL 접속 → 구글 계정 로그인 → 코드 입력
```

**PC 인증 정보를 NAS로 복사:**
```python
# PC의 credentials를 NAS 볼륨에 직접 복사
src = "C:/Users/user/.claude/.credentials.json"
dst = "/var/services/homes/b17314/.dockerimages/claude_controltower/.claude_sudapapalinux/.credentials.json"
```

### Gemini 인증

Gemini CLI는 Google OAuth로 `~/.gemini/oauth_creds.json`에 저장됩니다.

**인증 방법 (PC):**
```bash
gemini auth login
# 브라우저 자동 열림 → Google 계정 로그인
```

**NAS 컨테이너에 복사:**
```
PC: C:/Users/user/.gemini/oauth_creds.json
NAS 볼륨: .gemini_sudapapalinux/oauth_creds.json
컨테이너 내: /home/appuser/.gemini/oauth_creds.json
```

---

## 데이터 흐름

### 메시지 처리 흐름

```
1. 텔레그램 메시지 수신
2. _check_allowed() → 허용된 사용자 확인
3. "⏳ 처리 중..." 즉시 응답
4. MessageQueue.enqueue() → 큐에 추가
5. worker가 _process_message() 실행
6. AISessionManager.ask(prompt) 호출
7.   └─ ClaudeSession.ask() 또는 GeminiSession.ask()
8. ChatHistoryStore에 저장
9. 응답 전송 (3000자 초과 시 파일)
10. "⏳ 처리 중..." 메시지 삭제
```

### 이미지 처리 흐름

```
1. 이미지 메시지 수신
2. Telegram 서버에서 이미지 다운로드
3. 임시 파일로 저장 (.jpg)
4. "[이미지 첨부됨: /tmp/xxx.jpg]\n{캡션}" 형태로 AI 전달
5. 응답 후 임시 파일 삭제
```

---

## 트러블슈팅

### ❌ "Not logged in" 오류

Claude CLI 인증이 만료됨.

**해결:** PC의 `.credentials.json`을 NAS 볼륨에 재복사

```python
# C:\temp\copy_credentials.py 실행
```

### ❌ Gemini 응답 없음

Gemini OAuth 토큰 만료 가능성.

**해결:** PC에서 `gemini auth login` 재실행 후 `oauth_creds.json` 재복사

### ❌ 컨테이너 응답없음

```bash
# 로그 확인
sudo docker logs controltower-sudapapalinux --tail 50

# 재시작
sudo docker restart controltower-sudapapalinux
```

### ❌ 빌드 실패 (scripts/ 폴더 없음)

Dockerfile이 scripts/ 폴더를 선택적으로 처리하므로 정상 동작해야 함.
`RUN mkdir -p /app/scripts` 가 Dockerfile에 있는지 확인.

### ⚠️ 메모리 부족

NAS에서 Docker 이미지가 너무 크면 메모리 부족 발생.
현재 이미지 크기: **1.74GB**

```bash
# 불필요한 이미지 정리
sudo docker image prune -f
```

---

## 개발 히스토리

| 버전 | 변경사항 |
|------|----------|
| v0.1 | 초기 버전 (Claude Code 단독) |
| v0.2 | pystray 제거, Docker/Linux 호환 |
| v0.3 | NAS 배포, SSH 원격 빌드 |
| v0.4 | Gemini CLI 통합, `/new` AI 선택 키보드 |
| v0.5 | ChatGPT 제거 (API Key 필요), Claude+Gemini OAuth 방식 확정 |

---

*최종 업데이트: 2026-02-21*

# telegram_claude_bot

텔레그램을 통해 다수의 Claude Code 인스턴스를 원격 제어하고 모니터링하는 시스템.

## 빠른 시작

### 1. 환경 설정

```bash
cp .env.example .env
# .env 파일 편집: TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_IDS 입력
```

### 2. 실행

```bash
pip install -e .
python -m src.main
```

또는 VS Code에서 **F5** (launch.json 설정 포함)

### 3. EXE 빌드

```bash
pip install pyinstaller
pyinstaller deploy/windows/telegram_claude_bot.spec --clean --noconfirm --workpath build/.tmp --distpath build
# build/telegram_claude_bot/ 폴더 생성됨 → 같은 폴더에 .env 파일 필요
```

---

## 텔레그램 명령어

### 기본 명령

| 명령어 | 설명 |
|--------|------|
| `/start` | 봇 시작 및 도움말 표시 |
| `/help` | `/start`와 동일 |
| `/status` | 전체 시스템 상태 요약 (인스턴스 수, 실행 중인 작업 수) |

### 인스턴스 관리

| 명령어 | 설명 |
|--------|------|
| `/instances` | 인스턴스 목록 조회 (인라인 키보드) |
| `/create <name> <dir> <api_key> [model]` | 새 인스턴스 생성 |
| `/stop <instance_id>` | 특정 인스턴스 중지 |
| `/stopall` | 모든 인스턴스 중지 |
| `/setmodel <instance_id> <model>` | 인스턴스 모델 변경 |

**`/create` 예시:**
```
/create mybot /home/user/project sk-ant-xxxxxxxx claude-opus-4-5
/create mybot /home/user/project sk-ant-xxxxxxxx
```
- `name`: 인스턴스 이름
- `dir`: 작업 디렉토리 경로
- `api_key`: Anthropic API 키
- `model` (선택): 사용할 모델 (기본값: `claude-opus-4-5`)

### 작업 실행

| 명령어 | 설명 |
|--------|------|
| `/run <instance_id> <prompt>` | 특정 인스턴스에 작업 실행 |
| `/logs <instance_id> [lines]` | 인스턴스 로그 조회 |

**`/run` 예시:**
```
/run inst-001 파이썬 파일을 분석하고 버그를 찾아줘
/run inst-001 README.md를 작성해줘
```

**`/logs` 예시:**
```
/logs inst-001
/logs inst-001 50
```

---

## 인라인 키보드 액션

`/instances` 명령 후 표시되는 인라인 키보드로 GUI처럼 제어 가능.

### 인스턴스 목록 화면
| 버튼 | 동작 |
|------|------|
| `🔴/🟢/⚠️ <이름> (<상태>)` | 인스턴스 상세 화면으로 이동 |
| `🔄 새로고침` | 목록 새로고침 |

### 인스턴스 상세 화면
| 버튼 | 동작 |
|------|------|
| `▶️ 작업 실행` | 프롬프트 입력 대화 시작 → 메시지 입력 → 작업 실행 |
| `📋 로그` | 최근 로그 조회 |
| `⏹ 중지` | 인스턴스 중지 (확인 후 실행) |
| `🗑 삭제` | 인스턴스 삭제 (확인 후 실행) |
| `📜 히스토리` | 최근 작업 목록 조회 |
| `« 목록으로` | 인스턴스 목록으로 돌아가기 |

### 확인 화면 (삭제/중지 시)
| 버튼 | 동작 |
|------|------|
| `✅ 확인` | 작업 실행 |
| `❌ 취소` | 취소 |

---

## 인스턴스 상태

| 상태 | 이모지 | 설명 |
|------|--------|------|
| `idle` | ⭕ | 대기 중 |
| `running` | 🟢 | 작업 실행 중 |
| `error` | ⚠️ | 오류 발생 |
| `stopped` | 🔴 | 중지됨 |

## 작업 상태

| 상태 | 이모지 | 설명 |
|------|--------|------|
| `pending` | ⏸ | 대기 중 |
| `running` | ⏳ | 실행 중 |
| `completed` | ✅ | 완료 |
| `failed` | ❌ | 실패 |
| `cancelled` | 🚫 | 취소됨 |

---

## .env 설정

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
ALLOWED_CHAT_IDS=[123456789]
MAX_CONCURRENT_INSTANCES=5
TASK_TIMEOUT_SECONDS=300
CLAUDE_CODE_PATH=claude
DATABASE_PATH=telegram_claude_bot.db
```

| 변수 | 필수 | 설명 |
|------|------|------|
| `TELEGRAM_BOT_TOKEN` | ✅ | @BotFather에서 발급받은 봇 토큰 |
| `ALLOWED_CHAT_IDS` | ✅ | 허용된 텔레그램 Chat ID 목록 (JSON 배열) |
| `MAX_CONCURRENT_INSTANCES` | - | 최대 동시 실행 인스턴스 수 (기본: 5) |
| `TASK_TIMEOUT_SECONDS` | - | 작업 타임아웃 (초, 기본: 300) |
| `CLAUDE_CODE_PATH` | - | Claude Code CLI 경로 (기본: `claude`) |
| `DATABASE_PATH` | - | SQLite DB 파일 경로 (기본: `telegram_claude_bot.db`) |

> **보안**: API 키와 봇 토큰은 `.env` 파일로만 관리. 텔레그램 명령어를 통한 변경 불가.

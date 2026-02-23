# Windows 배포 가이드

## 방법 1: 원클릭 설치 (권장)

### 실행 방법

1. `deploy/windows/install.bat` 더블클릭
2. 화면 안내에 따라 진행

### install.bat이 하는 일

1. **Python 3.11+** 설치 확인 및 자동 설치 (winget 사용)
2. **Node.js LTS** 설치 확인 및 자동 설치 (winget 사용)
3. **Claude CLI** (`@anthropic-ai/claude-code`) 설치 확인 및 자동 설치 (npm 사용)
4. **가상환경** (`.venv`) 생성 및 패키지 자동 설치 (`pip install -e .`)
5. **.env** 설정 파일 자동 생성 후 메모장으로 편집기 오픈
6. **봇 자동 시작**

### 재실행

이미 설치된 경우 `install.bat`을 다시 실행하면 설치 단계를 건너뛰고 봇만 시작됩니다.

### winget이 없는 경우

winget이 없으면 스크립트가 직접 설치 링크를 안내합니다.

- Python: https://www.python.org/downloads/ (설치 시 "Add Python to PATH" 체크 필수)
- Node.js: https://nodejs.org/

직접 설치 완료 후 `install.bat`을 다시 실행하세요.

---

## 방법 2: EXE 빌드

소스 코드 없이 단독 실행 파일로 배포할 때 사용합니다.

### 빌드 준비

```cmd
pip install pyinstaller
```

### 빌드 실행

프로젝트 루트에서 실행:

```cmd
pyinstaller deploy/windows/controltower.spec --clean --noconfirm
```

### 빌드 결과

```
dist/
  telegram_claude_bot/
    telegram_claude_bot.exe   <- 실행 파일
    _internal/                <- 런타임 의존성
```

### 배포

`dist/telegram_claude_bot/` 폴더 전체를 복사하여 배포합니다.

- 실행 전 같은 폴더에 `.env` 파일을 위치시켜야 합니다.
- `telegram_claude_bot.exe`를 실행합니다.

---

## .env 설정

### 필수 항목

```
TELEGRAM_BOT_TOKEN=your-bot-token-here
TELEGRAM_CHAT_ID=[123456789]
```

- `TELEGRAM_BOT_TOKEN`: 텔레그램 @BotFather에서 발급받은 봇 토큰
- `TELEGRAM_CHAT_ID`: 허용할 사용자의 Chat ID (대괄호 필수)
  - 다수 허용: `[123456789, 987654321]`
  - Chat ID 확인: 텔레그램에서 @userinfobot 에 메시지 전송

### 선택 항목

```
CLAUDE_CODE_PATH=claude
DEFAULT_MODEL=claude-sonnet-4-6
CLAUDE_WORKSPACE=C:/Users/사용자명/projects
MAX_CONCURRENT=3
SESSION_POOL_SIZE=3
```

---

## Claude CLI 인증

봇 최초 실행 전 Claude CLI 인증이 필요합니다.

```cmd
claude
```

처음 실행 시 브라우저가 열리며 Anthropic 계정으로 로그인하면 인증이 완료됩니다.
인증 정보는 로컬에 저장되어 이후 재인증이 필요 없습니다.

---

## 문제 해결

### "python을 찾을 수 없습니다" 오류

Python 설치 후 터미널을 완전히 종료하고 `install.bat`을 다시 실행하세요.
또는 Python 설치 시 "Add Python to PATH" 옵션을 체크했는지 확인하세요.

### "claude를 찾을 수 없습니다" 오류

Node.js 설치 후 터미널을 완전히 종료하고 `install.bat`을 다시 실행하세요.
Node.js 설치 후 PATH가 갱신되지 않은 경우 발생합니다.

### 봇이 응답하지 않는 경우

1. `.env`의 `TELEGRAM_BOT_TOKEN` 값이 올바른지 확인
2. `TELEGRAM_CHAT_ID`가 대괄호와 함께 설정되어 있는지 확인: `[123456789]`
3. Claude CLI 인증이 완료되었는지 확인: `claude` 명령 실행

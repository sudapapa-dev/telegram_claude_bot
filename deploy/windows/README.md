# Windows 배포 가이드

## EXE 배포 (권장)

소스 코드 없이 단독 실행 파일로 배포합니다.

### 빌드

```cmd
pip install pyinstaller
pyinstaller deploy/windows/telegram_claude_bot.spec --clean --noconfirm --workpath build/.tmp --distpath dist
```

### 빌드 결과

```
dist/telegram_claude_bot/
  telegram_claude_bot.exe     <- 실행 파일
  _internal/                  <- 런타임 의존성
  install.bat                 <- 환경 설치 스크립트
  install_service.bat         <- NSSM 서비스 등록
  install_service.ps1
  remove_service.bat          <- NSSM 서비스 제거
  remove_service.ps1
  .env.example                <- 설정 파일 템플릿
  scripts/                    <- 스크립트 디렉토리
```

### 설치 및 실행

1. `dist/telegram_claude_bot/` 폴더 전체를 배포 대상에 복사
2. `install.bat` 더블클릭 — 필수 환경을 자동 설치합니다

### install.bat이 하는 일

1. **Node.js LTS** 설치 확인 및 자동 설치 (winget 사용)
2. **Claude CLI** (`@anthropic-ai/claude-code`) 설치 확인 및 자동 설치 (npm 사용)
3. **Notion MCP** 모듈 설치 확인 및 자동 설치 (선택적)
4. **.env** 설정 파일 자동 생성 후 메모장으로 편집

설치 완료 후 `telegram_claude_bot.exe`를 직접 실행하거나, NSSM 서비스로 등록할 수 있습니다.

### winget이 없는 경우

스크립트가 직접 설치 링크를 안내합니다. 수동 설치 후 `install.bat`을 다시 실행하세요.

- Node.js: https://nodejs.org/

---

## NSSM 서비스 등록 (선택)

Windows 부팅 시 자동 시작하려면 NSSM 서비스로 등록합니다.

1. `install_service.bat` 더블클릭 (관리자 권한 자동 요청)
2. Windows 로그인 비밀번호 입력 (현재 사용자 계정으로 서비스 실행)
3. 서비스 시작 여부 선택

서비스는 현재 사용자 계정으로 실행되며, Claude CLI 인증과 PATH가 자동으로 적용됩니다.
NSSM이 없으면 winget/choco로 자동 설치를 시도합니다.

서비스 제거: `remove_service.bat` 더블클릭

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
DEFAULT_MODEL=claude-sonnet-4-6
DEFAULT_SESSION_NAME=suho
SYSTEM_PROMPT_1=You are a highly capable Task Manager.
NOTION_TOKEN=
```

> `CLAUDE_CODE_PATH`는 설정하지 않아도 됩니다. 앱이 시작 시 자동으로 claude CLI 절대 경로를 탐지합니다.

---

## Claude CLI 인증

봇 최초 실행 전 Claude CLI 인증이 필요합니다.

```cmd
claude login
```

브라우저가 열리며 Anthropic 계정으로 로그인하면 인증이 완료됩니다.
인증 정보는 `%USERPROFILE%\.claude\.credentials.json`에 저장됩니다.

### Windows 서비스로 실행 시

`install_service.bat`으로 등록한 서비스는 현재 사용자 계정으로 실행되므로 인증이 자동 적용됩니다.
`CLAUDE_CODE_PATH`를 별도 설정하지 않아도 앱이 자동으로 공통 설치 경로에서 탐지합니다.

---

## 문제 해결

### "python을 찾을 수 없습니다" 오류

Python 설치 후 터미널을 완전히 종료하고 `install.bat`을 다시 실행하세요.
또는 Python 설치 시 "Add Python to PATH" 옵션을 체크했는지 확인하세요.

### "claude를 찾을 수 없습니다" 오류

Node.js 설치 후 터미널을 완전히 종료하고 `install.bat`을 다시 실행하세요.
Node.js 설치 후 PATH가 갱신되지 않은 경우 발생합니다.

### WinError 2 (서비스 환경)

NSSM 등으로 Windows 서비스 등록 후 `[WinError 2] 지정된 파일을 찾을 수 없습니다` 오류가 발생하면,
서비스 환경에서 PATH가 다르기 때문입니다. 앱이 자동으로 공통 설치 경로를 탐지하지만,
그래도 실패하면 `.env`에 절대 경로를 설정하세요:

```
CLAUDE_CODE_PATH=C:\Users\사용자명\.local\bin\claude.exe
```

### 봇이 응답하지 않는 경우

1. `.env`의 `TELEGRAM_BOT_TOKEN` 값이 올바른지 확인
2. `TELEGRAM_CHAT_ID`가 대괄호와 함께 설정되어 있는지 확인: `[123456789]`
3. Claude CLI 인증이 완료되었는지 확인: `claude login` 실행

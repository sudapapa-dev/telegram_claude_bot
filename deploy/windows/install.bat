@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ============================================================
:: telegram_claude_bot - Windows 원클릭 설치 및 실행 스크립트
:: 더블클릭으로 전체 환경 설치 후 봇을 자동 시작합니다.
:: ============================================================

:: 프로젝트 루트로 이동 (deploy\windows\ 기준 두 단계 위)
cd /d "%~dp0..\.."
set "PROJECT_ROOT=%CD%"

echo.
echo ============================================================
echo  telegram_claude_bot 설치 및 실행 스크립트
echo  프로젝트 경로: %PROJECT_ROOT%
echo ============================================================
echo.

:: ============================================================
:: 단계 1: Python 3.11+ 설치 확인
:: ============================================================
echo [1/5] Python 3.11+ 설치 확인 중...

set "PYTHON_OK=0"
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"

:: "Python 3.X.Y" 에서 메이저.마이너 추출
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do (
    for /f "tokens=1,2 delims=." %%a in ("%%v") do (
        set "PY_MAJOR=%%a"
        set "PY_MINOR=%%b"
    )
)

if defined PY_MAJOR (
    if !PY_MAJOR! GEQ 3 (
        if !PY_MINOR! GEQ 11 (
            echo     [OK] Python !PY_MAJOR!.!PY_MINOR! 이미 설치됨
            set "PYTHON_OK=1"
        )
    )
)

if "!PYTHON_OK!"=="0" (
    echo     [INFO] Python 3.11 이상이 필요합니다. 자동 설치를 시도합니다...
    where winget >nul 2>&1
    if !errorlevel! EQU 0 (
        echo     [INFO] winget으로 Python 3.11 설치 중... (시간이 걸릴 수 있습니다)
        winget install Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
        if !errorlevel! NEQ 0 (
            echo.
            echo     [ERROR] Python 자동 설치에 실패했습니다.
            echo     아래 링크에서 Python 3.11 이상을 직접 설치해 주세요:
            echo     https://www.python.org/downloads/
            echo     설치 시 "Add Python to PATH" 옵션을 반드시 체크하세요.
            echo.
            pause
            exit /b 1
        )
        :: PATH 갱신
        call :RefreshPath
        echo     [OK] Python 설치 완료
    ) else (
        echo.
        echo     [ERROR] winget을 찾을 수 없습니다.
        echo     아래 링크에서 Python 3.11 이상을 직접 설치해 주세요:
        echo     https://www.python.org/downloads/
        echo     설치 시 "Add Python to PATH" 옵션을 반드시 체크하세요.
        echo     설치 완료 후 이 스크립트를 다시 실행하세요.
        echo.
        pause
        exit /b 1
    )
)

:: pip 동작 확인
python -m pip --version >nul 2>&1
if !errorlevel! NEQ 0 (
    echo     [ERROR] pip를 사용할 수 없습니다. Python 설치 상태를 확인해 주세요.
    pause
    exit /b 1
)

:: ============================================================
:: 단계 2: Node.js 설치 확인
:: ============================================================
echo.
echo [2/5] Node.js 설치 확인 중...

node --version >nul 2>&1
if !errorlevel! EQU 0 (
    for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo     [OK] Node.js %%v 이미 설치됨
) else (
    echo     [INFO] Node.js가 설치되지 않았습니다. 자동 설치를 시도합니다...
    where winget >nul 2>&1
    if !errorlevel! EQU 0 (
        echo     [INFO] winget으로 Node.js LTS 설치 중... (시간이 걸릴 수 있습니다)
        winget install OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements
        if !errorlevel! NEQ 0 (
            echo.
            echo     [ERROR] Node.js 자동 설치에 실패했습니다.
            echo     아래 링크에서 Node.js LTS를 직접 설치해 주세요:
            echo     https://nodejs.org/
            echo     설치 완료 후 이 스크립트를 다시 실행하세요.
            echo.
            pause
            exit /b 1
        )
        call :RefreshPath
        echo     [OK] Node.js 설치 완료
    ) else (
        echo.
        echo     [ERROR] winget을 찾을 수 없습니다.
        echo     아래 링크에서 Node.js LTS를 직접 설치해 주세요:
        echo     https://nodejs.org/
        echo     설치 완료 후 이 스크립트를 다시 실행하세요.
        echo.
        pause
        exit /b 1
    )
)

:: ============================================================
:: 단계 3: Claude CLI 설치 확인
:: ============================================================
echo.
echo [3/5] Claude CLI 설치 확인 중...

claude --version >nul 2>&1
if !errorlevel! EQU 0 (
    for /f "tokens=*" %%v in ('claude --version 2^>^&1') do echo     [OK] Claude CLI %%v 이미 설치됨
) else (
    echo     [INFO] Claude CLI가 설치되지 않았습니다. npm으로 설치 중...
    npm install -g @anthropic-ai/claude-code
    if !errorlevel! NEQ 0 (
        echo.
        echo     [ERROR] Claude CLI 설치에 실패했습니다.
        echo     Node.js가 올바르게 설치되었는지 확인하고, 아래 명령을 직접 실행해 보세요:
        echo     npm install -g @anthropic-ai/claude-code
        echo.
        pause
        exit /b 1
    )
    call :RefreshPath
    echo     [OK] Claude CLI 설치 완료
)

:: ============================================================
:: 단계 4: 가상환경 생성 및 패키지 설치
:: ============================================================
echo.
echo [4/5] Python 가상환경 및 패키지 설치 중...

if not exist "%PROJECT_ROOT%\.venv" (
    echo     [INFO] 가상환경 생성 중...
    python -m venv "%PROJECT_ROOT%\.venv"
    if !errorlevel! NEQ 0 (
        echo     [ERROR] 가상환경 생성에 실패했습니다.
        pause
        exit /b 1
    )
    echo     [OK] 가상환경 생성 완료
) else (
    echo     [OK] 가상환경 이미 존재함 (.venv)
)

echo     [INFO] 패키지 설치 중 (pip install -e .)...
"%PROJECT_ROOT%\.venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
"%PROJECT_ROOT%\.venv\Scripts\pip.exe" install -e "%PROJECT_ROOT%" --quiet
if !errorlevel! NEQ 0 (
    echo.
    echo     [ERROR] 패키지 설치에 실패했습니다.
    echo     아래 명령을 직접 실행하여 오류를 확인하세요:
    echo     %PROJECT_ROOT%\.venv\Scripts\pip.exe install -e %PROJECT_ROOT%
    echo.
    pause
    exit /b 1
)
echo     [OK] 패키지 설치 완료

:: ============================================================
:: 단계 5: .env 파일 설정
:: ============================================================
echo.
echo [5/5] 환경 설정 파일 확인 중...

if not exist "%PROJECT_ROOT%\.env" (
    if exist "%PROJECT_ROOT%\.env.example" (
        copy "%PROJECT_ROOT%\.env.example" "%PROJECT_ROOT%\.env" >nul
        echo     [INFO] .env.example을 복사하여 .env 파일을 생성했습니다.
    ) else (
        echo     [INFO] .env 파일을 새로 생성합니다.
        (
            echo # Telegram Bot
            echo TELEGRAM_BOT_TOKEN=your-telegram-bot-token
            echo TELEGRAM_CHAT_ID=[123456789]
            echo.
            echo # Claude Code
            echo CLAUDE_CODE_PATH=claude
            echo DEFAULT_MODEL=claude-sonnet-4-6
            echo CLAUDE_WORKSPACE=C:/Users/%USERNAME%/projects
            echo.
            echo # Database
            echo DATABASE_PATH=./telegram_claude_bot.db
            echo.
            echo # 최대 동시 Claude 인스턴스 수
            echo MAX_CONCURRENT=3
            echo SESSION_POOL_SIZE=3
        ) > "%PROJECT_ROOT%\.env"
    )
    echo.
    echo     ============================================================
    echo      중요: .env 파일에 텔레그램 봇 설정이 필요합니다.
    echo     ============================================================
    echo      메모장이 열리면 아래 값을 반드시 설정하세요:
    echo.
    echo        TELEGRAM_BOT_TOKEN  = 텔레그램 BotFather에서 발급받은 토큰
    echo        TELEGRAM_CHAT_ID    = 허용할 사용자의 Chat ID (대괄호 포함)
    echo                              예: [123456789]
    echo                              예: [123456789, 987654321]  (다수 허용)
    echo.
    echo      Chat ID 확인 방법: @userinfobot 에 메시지 전송
    echo     ============================================================
    echo.
    echo     메모장에서 설정을 저장(Ctrl+S)하고 닫은 후 엔터를 눌러주세요.
    echo.
    start "" notepad "%PROJECT_ROOT%\.env"
    pause
) else (
    echo     [OK] .env 파일 이미 존재함

    :: TELEGRAM_BOT_TOKEN 기본값 확인
    findstr /C:"TELEGRAM_BOT_TOKEN=your-telegram-bot-token" "%PROJECT_ROOT%\.env" >nul 2>&1
    if !errorlevel! EQU 0 (
        echo.
        echo     [경고] .env 파일에 아직 기본값이 설정되어 있습니다.
        echo     메모장이 열리면 TELEGRAM_BOT_TOKEN과 TELEGRAM_CHAT_ID를 설정하세요.
        echo     설정 저장 후 메모장을 닫고 엔터를 눌러주세요.
        echo.
        start "" notepad "%PROJECT_ROOT%\.env"
        pause
    )
)

:: .env 최종 검증
findstr /C:"TELEGRAM_BOT_TOKEN=" "%PROJECT_ROOT%\.env" >nul 2>&1
if !errorlevel! NEQ 0 (
    echo.
    echo     [ERROR] .env 파일에 TELEGRAM_BOT_TOKEN이 없습니다.
    echo     %PROJECT_ROOT%\.env 파일을 직접 편집해 주세요.
    echo.
    pause
    exit /b 1
)

:: ============================================================
:: Claude CLI 인증 안내
:: ============================================================
echo.
echo ============================================================
echo  Claude CLI 인증 안내
echo ============================================================
echo  처음 실행 시 Claude CLI 인증이 필요합니다.
echo  봇 실행 후 별도 터미널에서 아래 명령을 실행하여 인증하세요:
echo.
echo    claude
echo.
echo  브라우저가 열리면 Anthropic 계정으로 로그인하여 인증을 완료하세요.
echo ============================================================
echo.

:: ============================================================
:: 봇 실행
:: ============================================================
echo ============================================================
echo  모든 준비 완료. telegram_claude_bot을 시작합니다.
echo  종료하려면 이 창에서 Ctrl+C를 누르세요.
echo ============================================================
echo.

"%PROJECT_ROOT%\.venv\Scripts\python.exe" -m src.main

if !errorlevel! NEQ 0 (
    echo.
    echo     [ERROR] 봇 실행 중 오류가 발생했습니다. (종료 코드: !errorlevel!)
    echo     위의 오류 메시지를 확인하고 .env 설정이 올바른지 확인하세요.
    echo.
    pause
)

goto :EOF

:: ============================================================
:: PATH 갱신 서브루틴
:: ============================================================
:RefreshPath
    for /f "skip=2 tokens=3*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do (
        if "%%b"=="" (set "SYS_PATH=%%a") else (set "SYS_PATH=%%a %%b")
    )
    for /f "skip=2 tokens=3*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do (
        if "%%b"=="" (set "USR_PATH=%%a") else (set "USR_PATH=%%a %%b")
    )
    set "PATH=!SYS_PATH!;!USR_PATH!"
    goto :EOF

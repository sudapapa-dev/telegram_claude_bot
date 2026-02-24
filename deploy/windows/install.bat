@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ============================================================
:: telegram_claude_bot - EXE 환경 설치 및 실행 스크립트
:: 더블클릭으로 필수 환경 설치 후 봇을 자동 시작합니다.
:: ============================================================

:: EXE와 같은 폴더 기준
set "APP_DIR=%~dp0"
if "%APP_DIR:~-1%"=="\" set "APP_DIR=%APP_DIR:~0,-1%"

echo.
echo ============================================================
echo  telegram_claude_bot - 환경 설치 및 실행
echo  경로: %APP_DIR%
echo ============================================================
echo.

:: ============================================================
:: 단계 1: Node.js 설치 확인
:: ============================================================
echo [1/4] Node.js 설치 확인 중...

node --version >nul 2>&1
if !errorlevel! EQU 0 (
    for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo     [OK] Node.js %%v 이미 설치됨
) else (
    echo     [INFO] Node.js가 설치되지 않았습니다. 자동 설치를 시도합니다...
    where winget >nul 2>&1
    if !errorlevel! EQU 0 (
        echo     [INFO] winget으로 Node.js LTS 설치 중...
        winget install OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements
        if !errorlevel! NEQ 0 (
            echo.
            echo     [ERROR] Node.js 자동 설치에 실패했습니다.
            echo     https://nodejs.org/ 에서 직접 설치해 주세요.
            echo.
            pause
            exit /b 1
        )
        call :RefreshPath
        echo     [OK] Node.js 설치 완료
    ) else (
        echo.
        echo     [ERROR] winget을 찾을 수 없습니다.
        echo     https://nodejs.org/ 에서 Node.js LTS를 직접 설치해 주세요.
        echo     설치 완료 후 이 스크립트를 다시 실행하세요.
        echo.
        pause
        exit /b 1
    )
)

:: ============================================================
:: 단계 2: Claude CLI 설치 확인
:: ============================================================
echo.
echo [2/4] Claude CLI 설치 확인 중...

claude --version >nul 2>&1
if !errorlevel! EQU 0 (
    for /f "tokens=*" %%v in ('claude --version 2^>^&1') do echo     [OK] Claude CLI %%v 이미 설치됨
) else (
    echo     [INFO] Claude CLI가 설치되지 않았습니다. npm으로 설치 중...
    npm install -g @anthropic-ai/claude-code
    if !errorlevel! NEQ 0 (
        echo.
        echo     [ERROR] Claude CLI 설치에 실패했습니다.
        echo     npm install -g @anthropic-ai/claude-code 를 직접 실행해 보세요.
        echo.
        pause
        exit /b 1
    )
    call :RefreshPath
    echo     [OK] Claude CLI 설치 완료
)

REM ============================================================
REM 단계 3: Notion MCP 모듈 설치
REM ============================================================
echo.
echo [3/4] Notion MCP 모듈 확인 중...

where npm >nul 2>&1
if !errorlevel! NEQ 0 (
    echo     [SKIP] npm 없음 - Notion MCP 설치 건너뜀
    goto :StepEnv
)

for /f "tokens=*" %%p in ('npm root -g 2^>nul') do set "NPM_GLOBAL=%%p"
if exist "!NPM_GLOBAL!\@notionhq\notion-mcp-server\package.json" (
    echo     [OK] Notion MCP 모듈 이미 설치됨
    goto :StepEnv
)

echo     [INFO] Notion MCP 모듈 설치 중...
npm install -g @notionhq/notion-mcp-server --quiet
if !errorlevel! EQU 0 (
    echo     [OK] Notion MCP 모듈 설치 완료
) else (
    echo     [경고] Notion MCP 설치 실패. 필요하면 직접 설치하세요:
    echo     npm install -g @notionhq/notion-mcp-server
)

:StepEnv

:: ============================================================
:: 단계 4: .env 파일 설정
:: ============================================================
echo.
echo [4/4] 환경 설정 파일 확인 중...

if not exist "%APP_DIR%\.env" (
    if exist "%APP_DIR%\.env.example" (
        copy "%APP_DIR%\.env.example" "%APP_DIR%\.env" >nul
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
            echo # DEFAULT_MODEL=claude-sonnet-4-6
            echo DEFAULT_SESSION_NAME=suho
            echo.
            echo # Notion MCP
            echo # NOTION_TOKEN=
            echo.
            echo # System Prompt
            echo # SYSTEM_PROMPT_1=You are a helpful assistant.
        ) > "%APP_DIR%\.env"
    )
    echo.
    echo     ============================================================
    echo      .env 파일에 텔레그램 봇 설정이 필요합니다.
    echo     ============================================================
    echo      메모장이 열리면 아래 값을 반드시 설정하세요:
    echo.
    echo        TELEGRAM_BOT_TOKEN  = BotFather에서 발급받은 토큰
    echo        TELEGRAM_CHAT_ID    = 허용할 Chat ID [대괄호 포함]
    echo.
    echo      Chat ID 확인: @userinfobot 에 메시지 전송
    echo     ============================================================
    echo.
    echo     메모장에서 저장 후 닫고 엔터를 눌러주세요.
    echo.
    start "" notepad "%APP_DIR%\.env"
    pause
) else (
    echo     [OK] .env 파일 이미 존재함

    findstr /C:"TELEGRAM_BOT_TOKEN=your-telegram-bot-token" "%APP_DIR%\.env" >nul 2>&1
    if !errorlevel! EQU 0 (
        echo.
        echo     [경고] .env에 아직 기본값이 설정되어 있습니다.
        echo     메모장에서 TELEGRAM_BOT_TOKEN과 TELEGRAM_CHAT_ID를 설정하세요.
        echo.
        start "" notepad "%APP_DIR%\.env"
        pause
    )
)

:: .env 최종 검증
findstr /C:"TELEGRAM_BOT_TOKEN=" "%APP_DIR%\.env" >nul 2>&1
if !errorlevel! NEQ 0 (
    echo.
    echo     [ERROR] .env 파일에 TELEGRAM_BOT_TOKEN이 없습니다.
    echo     %APP_DIR%\.env 파일을 직접 편집해 주세요.
    echo.
    pause
    exit /b 1
)

:: ============================================================
:: 완료
:: ============================================================
echo.
echo ============================================================
echo  환경 설치 완료!
echo ============================================================
echo.
echo  봇 실행: telegram_claude_bot.exe
echo.
echo  처음 실행 시 Claude CLI 인증이 필요합니다.
echo  별도 터미널에서 'claude' 명령을 실행하여 인증하세요.
echo  브라우저가 열리면 Anthropic 계정으로 로그인하세요.
echo.
pause
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

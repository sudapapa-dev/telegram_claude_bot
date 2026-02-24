@echo off
chcp 65001 >nul
setlocal

set SERVICE_NAME=TelegramClaudeBot
set SCRIPT_DIR=%~dp0
set PS1=%SCRIPT_DIR%install_service.ps1

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"

endlocal

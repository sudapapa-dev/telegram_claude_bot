@echo off
chcp 65001 >nul
setlocal

set SCRIPT_DIR=%~dp0
set PS1=%SCRIPT_DIR%remove_service.ps1

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"

endlocal

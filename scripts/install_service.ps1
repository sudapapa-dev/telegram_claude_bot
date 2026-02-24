# telegram_claude_bot Windows 서비스 등록 스크립트 (개발용)
# 관리자 권한으로 실행 필요
# 사용법: .\install_service.ps1 [-Action install|uninstall|start|stop|status]

param(
    [string]$Action = "install"  # install | uninstall | start | stop | status
)

$ServiceName = "TelegramClaudeBot"
$DisplayName = "Telegram Claude Bot"
$Description = "Claude Code Orchestration Bot via Telegram"

# EXE 경로: 프로젝트 루트 기준 build 폴더
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $ScriptDir ".."))
$ExePath = Join-Path $ProjectRoot "build\telegram_claude_bot\telegram_claude_bot.exe"
$ExePath = [System.IO.Path]::GetFullPath($ExePath)
$AppDir = Split-Path -Parent $ExePath

# 관리자 권한 확인
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "[오류] 관리자 권한으로 실행해주세요." -ForegroundColor Red
    Write-Host "PowerShell을 우클릭 -> '관리자로 실행' 후 다시 시도하세요."
    exit 1
}

# ── NSSM 확인 ──
function Get-NssmPath {
    $nssm = Get-Command nssm -ErrorAction SilentlyContinue
    if (-not $nssm) {
        Write-Host "[오류] NSSM이 설치되지 않았습니다." -ForegroundColor Red
        Write-Host "아래 명령으로 설치하세요:" -ForegroundColor Yellow
        Write-Host "  winget install NSSM.NSSM"
        Write-Host "  choco install nssm"
        exit 1
    }
    return $nssm.Source
}

function Install-Service {
    if (-not (Test-Path $ExePath)) {
        Write-Host "[오류] EXE 파일을 찾을 수 없습니다: $ExePath" -ForegroundColor Red
        Write-Host "먼저 EXE를 빌드하세요: pyinstaller deploy/windows/telegram_claude_bot.spec --workpath build/.tmp --distpath build"
        exit 1
    }

    $NssmPath = Get-NssmPath

    $existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "[정보] 기존 서비스가 존재합니다. 먼저 제거합니다..." -ForegroundColor Yellow
        Uninstall-Service
    }

    Write-Host "서비스 등록 중: $DisplayName" -ForegroundColor Cyan
    Write-Host "  EXE: $ExePath"

    & $NssmPath install $ServiceName "$ExePath"
    & $NssmPath set $ServiceName DisplayName "$DisplayName" 2>&1 | Out-Null
    & $NssmPath set $ServiceName Description "$Description" 2>&1 | Out-Null
    & $NssmPath set $ServiceName AppDirectory "$AppDir" 2>&1 | Out-Null
    & $NssmPath set $ServiceName Start SERVICE_AUTO_START 2>&1 | Out-Null
    & $NssmPath set $ServiceName AppRestartDelay 60000 2>&1 | Out-Null
    & $NssmPath set $ServiceName AppExit Default Restart 2>&1 | Out-Null

    # 로그
    $LogDir = Join-Path $AppDir "logs"
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
    & $NssmPath set $ServiceName AppStdout (Join-Path $LogDir "service_stdout.log") 2>&1 | Out-Null
    & $NssmPath set $ServiceName AppStderr (Join-Path $LogDir "service_stderr.log") 2>&1 | Out-Null
    & $NssmPath set $ServiceName AppStdoutCreationDisposition 4 2>&1 | Out-Null
    & $NssmPath set $ServiceName AppStderrCreationDisposition 4 2>&1 | Out-Null

    Write-Host "[완료] 서비스 등록 완료" -ForegroundColor Green

    $start = Read-Host "지금 서비스를 시작할까요? (y/n)"
    if ($start -eq "y" -or $start -eq "Y") {
        Start-ServiceAction
    }
}

function Uninstall-Service {
    $NssmPath = Get-NssmPath
    $existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $existing) {
        Write-Host "[정보] 등록된 서비스가 없습니다." -ForegroundColor Yellow
        return
    }

    if ($existing.Status -eq "Running") {
        Write-Host "서비스 중지 중..."
        & $NssmPath stop $ServiceName 2>&1 | Out-Null
        Start-Sleep -Seconds 2
    }

    & $NssmPath remove $ServiceName confirm 2>&1 | Out-Null
    Write-Host "[완료] 서비스 제거 완료" -ForegroundColor Green
}

function Start-ServiceAction {
    $NssmPath = Get-NssmPath
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Host "[오류] 서비스가 등록되어 있지 않습니다. 먼저 install을 실행하세요." -ForegroundColor Red
        exit 1
    }
    & $NssmPath start $ServiceName
    Start-Sleep -Seconds 3
    $svc = Get-Service -Name $ServiceName
    $svc.Refresh()
    Write-Host "[완료] 서비스 시작됨: $($svc.Status)" -ForegroundColor Green
}

function Stop-ServiceAction {
    $NssmPath = Get-NssmPath
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Host "[오류] 서비스가 등록되어 있지 않습니다." -ForegroundColor Red
        exit 1
    }
    & $NssmPath stop $ServiceName
    Write-Host "[완료] 서비스 중지됨" -ForegroundColor Green
}

function Show-Status {
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Host "서비스 상태: [미등록]" -ForegroundColor Yellow
    } else {
        $color = if ($svc.Status -eq "Running") { "Green" } else { "Red" }
        Write-Host "서비스 상태: $($svc.Status)" -ForegroundColor $color
        Write-Host "  이름: $($svc.DisplayName)"
        Write-Host "  시작 유형: $($svc.StartType)"
    }
}

switch ($Action.ToLower()) {
    "install"   { Install-Service }
    "uninstall" { Uninstall-Service }
    "start"     { Start-ServiceAction }
    "stop"      { Stop-ServiceAction }
    "status"    { Show-Status }
    default {
        Write-Host "사용법: .\install_service.ps1 [-Action install|uninstall|start|stop|status]"
        Write-Host ""
        Write-Host "  install   - NSSM으로 서비스 등록 및 자동 재시작 설정"
        Write-Host "  uninstall - 서비스 제거"
        Write-Host "  start     - 서비스 시작"
        Write-Host "  stop      - 서비스 중지"
        Write-Host "  status    - 서비스 상태 확인"
    }
}

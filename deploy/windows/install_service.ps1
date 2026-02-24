# Telegram Claude Bot - NSSM 기반 서비스 등록 스크립트
# 이 파일을 telegram_claude_bot.exe 와 같은 폴더에 복사해서 사용하세요.
# 우클릭 -> "PowerShell로 실행" 또는 관리자 PowerShell에서 실행

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ServiceName = "TelegramClaudeBot"
$DisplayName = "Telegram Claude Bot"
$Description = "Claude Code Orchestration Bot via Telegram"

# EXE 경로: 이 스크립트와 같은 폴더에 위치한 EXE
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ExePath = Join-Path $ScriptDir "telegram_claude_bot.exe"
$ExePath = [System.IO.Path]::GetFullPath($ExePath)

# 관리자 권한 확인 및 자동 재요청
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "관리자 권한이 필요합니다. 관리자 모드로 재시작합니다..." -ForegroundColor Yellow
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`""
    exit
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Telegram Claude Bot - 서비스 등록" -ForegroundColor Cyan
Write-Host "  (NSSM 기반)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── EXE 존재 확인 ──
if (-not (Test-Path $ExePath)) {
    Write-Host "[오류] EXE 파일을 찾을 수 없습니다:" -ForegroundColor Red
    Write-Host "  $ExePath" -ForegroundColor Red
    Write-Host ""
    Write-Host "이 스크립트를 telegram_claude_bot.exe 와 같은 폴더에 복사한 후 실행하세요."
    Write-Host ""
    Read-Host "엔터를 눌러 종료"
    exit 1
}

# ── .env 존재 확인 ──
$EnvPath = Join-Path $ScriptDir ".env"
if (-not (Test-Path $EnvPath)) {
    Write-Host "[경고] .env 파일이 없습니다: $EnvPath" -ForegroundColor Yellow
    Write-Host "서비스 등록 전에 .env 파일을 먼저 생성하세요."
    Write-Host ""
    $cont = Read-Host ".env 없이 계속 진행할까요? (y/n)"
    if ($cont -ne "y" -and $cont -ne "Y") {
        exit 0
    }
}

# ── NSSM 설치 확인 및 자동 설치 ──
function Install-NSSM {
    $nssm = Get-Command nssm -ErrorAction SilentlyContinue
    if ($nssm) {
        Write-Host "[OK] NSSM 이미 설치됨: $($nssm.Source)" -ForegroundColor Green
        return $nssm.Source
    }

    Write-Host "[INFO] NSSM이 설치되지 않았습니다. 자동 설치를 시도합니다..." -ForegroundColor Yellow

    # winget 시도
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "  winget으로 NSSM 설치 중..." -ForegroundColor Cyan
        winget install NSSM.NSSM --silent --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null

        # PATH 갱신
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                     [System.Environment]::GetEnvironmentVariable("Path", "User")

        $nssm = Get-Command nssm -ErrorAction SilentlyContinue
        if ($nssm) {
            Write-Host "[OK] NSSM 설치 완료" -ForegroundColor Green
            return $nssm.Source
        }
    }

    # choco 시도
    $choco = Get-Command choco -ErrorAction SilentlyContinue
    if ($choco) {
        Write-Host "  choco로 NSSM 설치 중..." -ForegroundColor Cyan
        choco install nssm -y 2>&1 | Out-Null

        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                     [System.Environment]::GetEnvironmentVariable("Path", "User")

        $nssm = Get-Command nssm -ErrorAction SilentlyContinue
        if ($nssm) {
            Write-Host "[OK] NSSM 설치 완료" -ForegroundColor Green
            return $nssm.Source
        }
    }

    # 실패
    Write-Host "[오류] NSSM 자동 설치에 실패했습니다." -ForegroundColor Red
    Write-Host ""
    Write-Host "아래 방법 중 하나로 직접 설치한 후 다시 실행하세요:" -ForegroundColor Yellow
    Write-Host "  winget install NSSM.NSSM"
    Write-Host "  choco install nssm"
    Write-Host "  https://nssm.cc/download"
    Write-Host ""
    Read-Host "엔터를 눌러 종료"
    exit 1
}

$NssmPath = Install-NSSM
Write-Host ""

# ── 기존 서비스 처리 ──
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[정보] 기존 서비스가 존재합니다. 먼저 제거 후 재등록합니다." -ForegroundColor Yellow
    if ($existing.Status -eq "Running") {
        & $NssmPath stop $ServiceName 2>&1 | Out-Null
        Start-Sleep -Seconds 2
    }
    & $NssmPath remove $ServiceName confirm 2>&1 | Out-Null
    Start-Sleep -Seconds 1
}

# ── NSSM으로 서비스 등록 ──
Write-Host "서비스 등록 중..." -ForegroundColor Cyan
Write-Host "  EXE: $ExePath"
Write-Host ""

& $NssmPath install $ServiceName "$ExePath"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[오류] 서비스 등록 실패" -ForegroundColor Red
    Read-Host "엔터를 눌러 종료"
    exit 1
}

# 서비스 설정
& $NssmPath set $ServiceName DisplayName "$DisplayName" 2>&1 | Out-Null
& $NssmPath set $ServiceName Description "$Description" 2>&1 | Out-Null
& $NssmPath set $ServiceName AppDirectory "$ScriptDir" 2>&1 | Out-Null
& $NssmPath set $ServiceName Start SERVICE_AUTO_START 2>&1 | Out-Null

# 서비스 로그온 계정: 현재 사용자 (SYSTEM 대신)
# SYSTEM 계정은 Claude CLI 인증 정보와 PATH가 없어 실행 불가
Write-Host ""
Write-Host "서비스 로그온 계정을 설정합니다." -ForegroundColor Cyan
Write-Host "SYSTEM 계정은 Claude CLI 인증/PATH가 없어 현재 사용자 계정이 필요합니다."
Write-Host ""
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
Write-Host "  현재 사용자: $currentUser"
$password = Read-Host "  Windows 로그인 비밀번호를 입력하세요" -AsSecureString
$plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($password))
& $NssmPath set $ServiceName ObjectName "$currentUser" "$plainPassword" 2>&1 | Out-Null
$plainPassword = $null
Write-Host "[OK] 서비스 로그온 계정: $currentUser" -ForegroundColor Green

# 사용자 환경변수 설정 (NSSM 서비스는 USERPROFILE/HOME을 자동 설정하지 않음)
$userProfile = [System.Environment]::GetFolderPath("UserProfile")
& $NssmPath set $ServiceName AppEnvironmentExtra "USERPROFILE=$userProfile" "HOME=$userProfile" "HOMEPATH=$userProfile" 2>&1 | Out-Null
Write-Host "[OK] 환경변수: USERPROFILE=$userProfile" -ForegroundColor Green

# 실패 시 자동 재시작 (60초 후, 최대 3회)
& $NssmPath set $ServiceName AppRestartDelay 60000 2>&1 | Out-Null
& $NssmPath set $ServiceName AppExit Default Restart 2>&1 | Out-Null

# stdout/stderr를 로그 파일로
$LogDir = Join-Path $ScriptDir "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
& $NssmPath set $ServiceName AppStdout (Join-Path $LogDir "service_stdout.log") 2>&1 | Out-Null
& $NssmPath set $ServiceName AppStderr (Join-Path $LogDir "service_stderr.log") 2>&1 | Out-Null
& $NssmPath set $ServiceName AppStdoutCreationDisposition 4 2>&1 | Out-Null
& $NssmPath set $ServiceName AppStderrCreationDisposition 4 2>&1 | Out-Null

Write-Host "[완료] 서비스 등록 완료!" -ForegroundColor Green
Write-Host ""
Write-Host "  서비스 이름: $ServiceName"
Write-Host "  시작 방식: 자동 (부팅 시 자동 실행)"
Write-Host "  오류 시: 60초 후 자동 재시작"
Write-Host "  로그: $LogDir"
Write-Host ""

# ── 서비스 시작 ──
$start = Read-Host "지금 서비스를 시작할까요? (y/n)"
if ($start -eq "y" -or $start -eq "Y") {
    & $NssmPath start $ServiceName
    Start-Sleep -Seconds 3
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -eq "Running") {
        Write-Host "[완료] 서비스 시작됨" -ForegroundColor Green
    } else {
        Write-Host "[경고] 서비스 상태: $($svc.Status)" -ForegroundColor Yellow
        Write-Host "로그를 확인하세요: $LogDir"
    }
}

Write-Host ""
Write-Host "서비스 관리: services.msc 또는 remove_service.ps1"
Write-Host ""
Read-Host "엔터를 눌러 종료"

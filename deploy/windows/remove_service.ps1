# Telegram Claude Bot - NSSM 기반 서비스 제거 스크립트
# 우클릭 -> "PowerShell로 실행" 또는 관리자 PowerShell에서 실행

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ServiceName = "TelegramClaudeBot"

# 관리자 권한 확인 및 자동 재요청
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "관리자 권한이 필요합니다. 관리자 모드로 재시작합니다..." -ForegroundColor Yellow
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`""
    exit
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Telegram Claude Bot - 서비스 제거" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $existing) {
    Write-Host "[정보] 등록된 서비스가 없습니다." -ForegroundColor Yellow
    Write-Host ""
    Read-Host "엔터를 눌러 종료"
    exit 0
}

Write-Host "서비스 정보:"
Write-Host "  이름: $($existing.DisplayName)"
Write-Host "  상태: $($existing.Status)"
Write-Host ""

$confirm = Read-Host "서비스를 제거할까요? (y/n)"
if ($confirm -ne "y" -and $confirm -ne "Y") {
    Write-Host "취소했습니다."
    Read-Host "엔터를 눌러 종료"
    exit 0
}

# NSSM 찾기
$nssm = Get-Command nssm -ErrorAction SilentlyContinue

if ($nssm) {
    # NSSM으로 제거
    if ($existing.Status -eq "Running") {
        Write-Host "서비스 중지 중..." -ForegroundColor Cyan
        & $nssm.Source stop $ServiceName 2>&1 | Out-Null
        Start-Sleep -Seconds 2
    }
    & $nssm.Source remove $ServiceName confirm 2>&1 | Out-Null
} else {
    # NSSM 없으면 sc.exe fallback
    Write-Host "[정보] NSSM을 찾을 수 없어 sc.exe로 제거합니다." -ForegroundColor Yellow
    if ($existing.Status -eq "Running") {
        Write-Host "서비스 중지 중..." -ForegroundColor Cyan
        Stop-Service -Name $ServiceName -Force
        Start-Sleep -Seconds 2
    }
    sc.exe delete $ServiceName | Out-Null
}

Start-Sleep -Seconds 1

$check = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $check) {
    Write-Host "[완료] 서비스가 제거되었습니다." -ForegroundColor Green
} else {
    Write-Host "[경고] 서비스 제거 후에도 목록에 남아있습니다. 재부팅 후 완전히 제거됩니다." -ForegroundColor Yellow
}

Write-Host ""
Read-Host "엔터를 눌러 종료"

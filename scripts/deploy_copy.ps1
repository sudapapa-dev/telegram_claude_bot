$srcDir = 'D:\telegram_claude_bot\dist\telegram_claude_bot'
$dstDir = 'C:\Private\telegram_claude_bot'

# EXE 복사
Copy-Item -Path "$srcDir\telegram_claude_bot.exe" -Destination "$dstDir\telegram_claude_bot.exe" -Force
Write-Host 'EXE 복사 완료'

# _internal: robocopy /MIR 로 동기화 (삭제 없이 덮어쓰기)
$srcInt = "$srcDir\_internal"
$dstInt = "$dstDir\_internal"
robocopy $srcInt $dstInt /MIR /IS /IT /NP /NFL /NDL | Out-Null
$count = (Get-ChildItem $dstInt -Recurse | Measure-Object).Count
Write-Host "_internal 복사 완료: $count 개 항목"

# 배포 스크립트 복사
foreach ($f in @('install.bat','install_service.bat','install_service.ps1','remove_service.bat','remove_service.ps1')) {
    $s = "$srcDir\$f"
    if (Test-Path $s) {
        Copy-Item -Path $s -Destination "$dstDir\$f" -Force
    }
}
Write-Host '스크립트 복사 완료'
Write-Host '모든 파일 업데이트 완료'

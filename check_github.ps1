# PowerShell GitHub Auth & Sync Status Checker
$OutputEncoding = [System.Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " GITHUB AUTH & REPOSITORY SYNC STATUS" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check saved credentials
$cmdkeyOut = cmdkey /list | Out-String
if ($cmdkeyOut -match "git:https://github.com") {
    Write-Host "[OK] Git Credential Manager token is saved in Windows Credential Manager." -ForegroundColor Green
} else {
    Write-Host "[WARN] No saved credentials found in Windows Credential Manager." -ForegroundColor Yellow
}

# 2. Non-interactive remote probe
$env:GIT_TERMINAL_PROMPT = "0"
$remoteCheck = git ls-remote --exit-code origin HEAD 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] GitHub authentication active! Access to origin verified." -ForegroundColor Green
} else {
    Write-Host "[ERROR] Authentication failed: cannot access origin." -ForegroundColor Red
    Write-Host "Run 'git push origin main' in terminal to log in." -ForegroundColor Yellow
    exit 1
}

# 3. Branch sync status
Write-Host ""
Write-Host "--- Branches Status ---" -ForegroundColor Cyan
$branches = @("main", "develop")
foreach ($b in $branches) {
    $null = git rev-parse --verify $b 2>&1
    if ($LASTEXITCODE -eq 0) {
        $aheadBehind = git rev-list --left-right --count "origin/$b...$b" 2>&1
        if ($LASTEXITCODE -eq 0) {
            $counts = ($aheadBehind -split "\s+") | Where-Object { $_ -ne "" }
            $behind = $counts[0]
            $ahead = $counts[1]
            if ($ahead -eq 0 -and $behind -eq 0) {
                Write-Host "  * Branch '$b': up-to-date with origin/$b [OK]" -ForegroundColor Green
            } elseif ($ahead -gt 0) {
                Write-Host "  * Branch '$b': $ahead commit(s) ahead of origin (push needed)" -ForegroundColor Yellow
            } elseif ($behind -gt 0) {
                Write-Host "  * Branch '$b': $behind commit(s) behind origin (pull needed)" -ForegroundColor Yellow
            }
        }
    }
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " Ready for automated git push / pull without re-login." -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

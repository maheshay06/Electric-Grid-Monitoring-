# First-time setup for Windows. Run from VS Code: Terminal > Run Task > "Setup (first time)",
# or:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# Safe to re-run: it never overwrites an existing backend\.env or database.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Need($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "$cmd not found. $hint" }
}
Need "node" "Install Node.js 20 or newer from https://nodejs.org"

# Python 3.10-3.13 (the py launcher is preferred on Windows)
$candidates = @(@("py", "-3.12"), @("py", "-3.13"), @("py", "-3.11"), @("py", "-3.10"), @("python"), @("python3"))
$pyExe = $null; $pyArgs = @()
foreach ($c in $candidates) {
    if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) { continue }
    $extra = @($c | Select-Object -Skip 1)
    & $c[0] @extra -c "import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $pyExe = $c[0]; $pyArgs = $extra; break }
}
if (-not $pyExe) { throw "Python 3.10 to 3.13 not found. Install from https://www.python.org (tick 'Add to PATH')." }
Write-Host "Using Python: $pyExe $pyArgs"

# Keep the venv path short: very long folder paths break scikit-learn on Windows.
if ($root.Length -gt 80) { Write-Warning "Project path is long ($($root.Length) chars). If pip fails with 'path too long', move the folder to something like C:\GridMonitor." }

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $pyExe @pyArgs -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# backend\.env
$envFile = "backend\.env"
if (-not (Test-Path $envFile)) {
    $secret = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
    (Get-Content "backend\.env.example") -replace "^JWT_SECRET=.*", "JWT_SECRET=$secret" | Set-Content $envFile -Encoding utf8
    Write-Host "Created backend\.env with a new random JWT_SECRET."

    $id = Read-Host "Choose an admin operator ID (3+ chars, letters/digits . _ -)"
    $sec = Read-Host "Choose an admin password (10+ chars, letter + digit, must not contain the ID)" -AsSecureString
    $pw = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
    (Get-Content $envFile) -replace "^SEED_ADMIN_OPERATOR_ID=.*", "SEED_ADMIN_OPERATOR_ID=$id" `
                           -replace "^SEED_ADMIN_PASSWORD=.*", "SEED_ADMIN_PASSWORD=$pw" | Set-Content $envFile -Encoding utf8
} else {
    Write-Host "backend\.env already exists - left untouched."
}

# database + Feeder 1 device key (printed ONCE - copy it into firmware config.h)
Push-Location backend
& ..\.venv\Scripts\python.exe seed.py
Pop-Location

# frontend
Push-Location frontend
npm install
Pop-Location

Write-Host ""
Write-Host "Setup complete. In VS Code run:  Terminal > Run Task > 'Run everything'"
Write-Host "Then open http://localhost:5173 and sign in with the admin ID you chose."
Write-Host "Tip: after first login you can delete SEED_ADMIN_PASSWORD from backend\.env."

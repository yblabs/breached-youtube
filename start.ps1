# ============================================================================
#  BREACHED YOUTUBE  ::  extraction node launcher
#  Starts the FastAPI engine (127.0.0.1:8000) and the Vite HUD (127.0.0.1:5173)
# ============================================================================

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

function Banner($text) {
    Write-Host ''
    Write-Host '  ==============================================' -ForegroundColor DarkCyan
    Write-Host "  BREACHED YOUTUBE :: $text" -ForegroundColor Cyan
    Write-Host '  ==============================================' -ForegroundColor DarkCyan
}

Banner 'SYSTEM DIAGNOSTICS'

# --- ffmpeg (required for 4K merge + MP3 extraction) ------------------------
$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpeg) {
    # winget installs to a per-session PATH; probe the install dir directly
    $wingetFfmpeg = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Gyan.FFmpeg_*" -Filter ffmpeg.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($wingetFfmpeg) {
        $env:Path = "$($wingetFfmpeg.DirectoryName);$env:Path"
        $ffmpeg = $wingetFfmpeg
    }
}
if ($ffmpeg) {
    Write-Host '  [OK]  FFMPEG ARMED' -ForegroundColor Green
} else {
    Write-Host '  [ERR] FFMPEG NOT FOUND -> winget install Gyan.FFmpeg' -ForegroundColor Red
    Write-Host '        4K MERGE AND MP3 EXTRACTION WILL FAIL.' -ForegroundColor Red
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) { Write-Host '  [OK]  PYTHON RUNTIME' -ForegroundColor Green }
else { Write-Host '  [ERR] PYTHON NOT FOUND' -ForegroundColor Red }

$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) { Write-Host '  [OK]  NODE JS RUNTIME (yt-dlp decryptor)' -ForegroundColor Green }
else { Write-Host '  [WARN] NODE NOT FOUND -> yt-dlp may miss some formats' -ForegroundColor Yellow }

# --- python deps -------------------------------------------------------------
Push-Location $backend
if (-not (Test-Path '.venv')) {
    Banner 'INSTALLING PYTHON DEPENDENCIES'
    python -m pip install -r requirements.txt
}
Pop-Location

# --- node deps ---------------------------------------------------------------
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
    Banner 'INSTALLING FRONTEND DEPENDENCIES'
    Push-Location $frontend
    npm install --no-fund --no-audit
    Pop-Location
}

# --- servers -----------------------------------------------------------------
Banner 'BOOTING EXTRACTION NODE // 127.0.0.1:8000'
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$backend'; python run_server.py"

Banner 'BOOTING HUD // 127.0.0.1:5173'
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$frontend'; npm run dev"

Start-Sleep -Seconds 3
Write-Host ''
Write-Host '  HUD       -> http://127.0.0.1:5173' -ForegroundColor Cyan
Write-Host '  API       -> http://127.0.0.1:8000/api/health' -ForegroundColor Cyan
Write-Host '  DOCS      -> http://127.0.0.1:8000/docs' -ForegroundColor Cyan
Write-Host ''

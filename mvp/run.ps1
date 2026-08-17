[CmdletBinding()]
param(
    [int]$Port = 8765,
    [string]$HostAddress = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvRoot = Join-Path $ProjectRoot '.venv'
$VenvPython = Join-Path $VenvRoot 'Scripts\python.exe'

if (-not (Test-Path -LiteralPath $VenvPython)) {
    python -m venv $VenvRoot
}

& $VenvPython -m pip install --disable-pip-version-check -q -r (Join-Path $ProjectRoot 'requirements.txt')

$env:PYTHONPATH = $ProjectRoot
$env:MVP_ENV = 'development'
$env:MVP_DB_PATH = Join-Path $ProjectRoot 'data\mvp.db'
$env:MVP_SILICON_MODE = 'mock'
$env:MVP_SITE_SMS_MODE = 'mock'
$env:MVP_REMOTE_BROWSER_MODE = 'disabled'
$env:MVP_SEED_DEMO = '1'
if (-not $env:MVP_SECRET) { $env:MVP_SECRET = 'local-mvp-secret-change-before-production' }
if (-not $env:MVP_ADMIN_KEY) { $env:MVP_ADMIN_KEY = 'mvp-admin-demo' }

& $VenvPython -m uvicorn mvp_app.main:app --host $HostAddress --port $Port

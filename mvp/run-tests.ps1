$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvRoot = Join-Path $ProjectRoot '.venv'
$VenvPython = Join-Path $VenvRoot 'Scripts\python.exe'

if (-not (Test-Path -LiteralPath $VenvPython)) {
    python -m venv $VenvRoot
}

& $VenvPython -m pip install --disable-pip-version-check -q -r (Join-Path $ProjectRoot 'requirements-dev.txt')

$env:PYTHONPATH = $ProjectRoot
Push-Location $ProjectRoot
try {
    & $VenvPython -m pytest -q
} finally {
    Pop-Location
}

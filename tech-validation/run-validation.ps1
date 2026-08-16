[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$evidence = Join-Path $root 'evidence'

function Invoke-Checked {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][scriptblock]$Action
    )

    Write-Host "[$Name] starting"
    & $Action
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "[$Name] failed with exit code $LASTEXITCODE"
    }
    Write-Host "[$Name] passed"
}

Invoke-Checked 'read-only-probe' {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'probe.ps1')
}
Invoke-Checked 'task-rules' {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'test-task-rules.ps1')
}
Invoke-Checked 'task-concurrency' {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'test-task-concurrency.ps1')
}
Invoke-Checked 'session-security' {
    & python (Join-Path $root 'test-session-security.py')
}
Invoke-Checked 'sensitive-output' {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'test-sensitive-output.ps1')
}

$ruleEvidence = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence 'task-rule-tests.json') | ConvertFrom-Json
$concurrencyEvidence = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence 'task-concurrency-tests.json') | ConvertFrom-Json
$securityEvidence = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence 'session-security-tests.json') | ConvertFrom-Json
$probeEvidence = Get-Content -Raw -Encoding UTF8 (Join-Path $evidence 'read-only-probe.json') | ConvertFrom-Json

$summary = [ordered]@{
    generatedAt = (Get-Date).ToUniversalTime().ToString('o')
    passed = $true
    safety = $probeEvidence.safety
    readOnlyEndpointPatterns = @($probeEvidence.discoveredEndpointPatterns).Count
    taskRuleScenarios = @($ruleEvidence.scenarios).Count
    concurrencyScenarios = @($concurrencyEvidence.scenarios).Count
    sessionSecurityScenarios = @($securityEvidence.scenarios).Count
    sensitiveOutputScan = 'passed'
}

$summaryPath = Join-Path $evidence 'validation-summary.json'
$summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 -Path $summaryPath
Write-Host "Validation package passed: $summaryPath"


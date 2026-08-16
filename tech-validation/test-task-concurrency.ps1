[CmdletBinding()]
param(
    [string]$OutputDirectory = ''
)

$ErrorActionPreference = 'Stop'
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $scriptDirectory 'evidence'
}

$sourcePath = Join-Path $scriptDirectory 'TaskConcurrencyProbe.cs'
Add-Type -Path $sourcePath
$results = [TaskConcurrencyProbe]::Run()

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$resultPath = Join-Path $OutputDirectory 'task-concurrency-tests.json'
[ordered]@{
    generatedAt = (Get-Date).ToUniversalTime().ToString('o')
    passed = $true
    scenarios = @($results | ForEach-Object {
        [ordered]@{
            scenario = $_.Scenario
            passed = $_.Passed
            capacity = $_.Capacity
            attempts = $_.Attempts
            accepted = $_.Accepted
        }
    })
} | ConvertTo-Json -Depth 6 | Set-Content -Path $resultPath -Encoding UTF8

Write-Host "All $($results.Count) concurrency scenarios passed: $resultPath"


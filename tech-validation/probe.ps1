[CmdletBinding()]
param(
    [string]$TargetUrl = 'http://tb.eq001.cn/choose/?source=5127688621175028142&step=0&type=gjld',
    [string]$TaskId = '5127688621175028142',
    [string]$OutputDirectory = ''
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
    $OutputDirectory = Join-Path $scriptDirectory 'evidence'
}

function Invoke-ReadOnlyRequest {
    param([Parameter(Mandatory)][string]$Uri)

    $started = Get-Date
    try {
        $response = Invoke-WebRequest -Uri $Uri -Method Get -UseBasicParsing -TimeoutSec 20
        [ordered]@{
            uri = $Uri
            ok = $true
            status = [int]$response.StatusCode
            contentType = [string]$response.Headers['Content-Type']
            contentLength = $response.RawContentLength
            elapsedMs = [int]((Get-Date) - $started).TotalMilliseconds
            content = [string]$response.Content
        }
    }
    catch {
        $status = $null
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $status = [int]$_.Exception.Response.StatusCode
        }
        [ordered]@{
            uri = $Uri
            ok = $false
            status = $status
            contentType = $null
            contentLength = 0
            elapsedMs = [int]((Get-Date) - $started).TotalMilliseconds
            error = $_.Exception.Message
            content = ''
        }
    }
}

function Get-Sha256 {
    param([Parameter(Mandatory)][string]$Text)

    $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
    $hash = [Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
    -join ($hash | ForEach-Object { $_.ToString('x2') })
}

function Redact-Config {
    param([Parameter(Mandatory)]$Config)

    $uidCount = 0
    if ($Config.uidList) { $uidCount = @($Config.uidList).Count }
    [ordered]@{
        needNum = $Config.needNum
        regNum = $Config.regNum
        authNum = $Config.authNum
        isEnableUidInvite = $Config.isEnableUidInvite
        hasShareId = -not [string]::IsNullOrWhiteSpace([string]$Config.shareId)
        hasInviterPhone = -not [string]::IsNullOrWhiteSpace([string]$Config.inviterPhone)
        uidListCount = $uidCount
    }
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

$page = Invoke-ReadOnlyRequest -Uri $TargetUrl
$scriptUrl = $null
if ($page.ok) {
    $scriptMatch = [regex]::Match($page.content, '<script[^>]+src=["''](?<src>[^"'']+\.js)["'']', 'IgnoreCase')
    if ($scriptMatch.Success) {
        $scriptUrl = [Uri]::new([Uri]$TargetUrl, $scriptMatch.Groups['src'].Value).AbsoluteUri
    }
}

$script = if ($scriptUrl) { Invoke-ReadOnlyRequest -Uri $scriptUrl } else { $null }
$configUrl = "https://p2.eq001.cn/gjld/task/config?tid=$([Uri]::EscapeDataString($TaskId))"
$configResponse = Invoke-ReadOnlyRequest -Uri $configUrl
$enableResponse = Invoke-ReadOnlyRequest -Uri 'https://p2.eq001.cn/gjld/enableUidInvite'

$endpointPatterns = @()
if ($script -and $script.ok) {
    $absolute = [regex]::Matches($script.content, 'https://p2\.eq001\.cn(?:/[A-Za-z0-9_?=&.%:{}$+~-]+)+') |
        ForEach-Object Value
    $relative = [regex]::Matches($script.content, '["''](?<path>/[A-Za-z0-9_?=&.%:{}$+~-]*(?:gjld|captcha|profile|task|invite|auth)[A-Za-z0-9_/?=&.%:{}$+~-]*)["'']') |
        ForEach-Object { $_.Groups['path'].Value }
    $endpointPatterns = @($absolute + $relative | Sort-Object -Unique)
}

$configData = $null
if ($configResponse.ok -and $configResponse.content) {
    try { $configData = $configResponse.content | ConvertFrom-Json } catch { $configData = $null }
}

$evidence = [ordered]@{
    generatedAt = (Get-Date).ToUniversalTime().ToString('o')
    safety = [ordered]@{
        methodsUsed = @('GET')
        smsTriggered = $false
        otpSubmitted = $false
        captchaSolved = $false
        orderCreated = $false
        paymentTriggered = $false
    }
    target = [ordered]@{
        url = $TargetUrl
        ok = $page.ok
        status = $page.status
        contentType = $page.contentType
        contentLength = $page.contentLength
        sha256 = if ($page.ok) { Get-Sha256 $page.content } else { $null }
    }
    frontendBundle = [ordered]@{
        url = $scriptUrl
        ok = if ($script) { $script.ok } else { $false }
        status = if ($script) { $script.status } else { $null }
        contentLength = if ($script) { $script.contentLength } else { 0 }
        sha256 = if ($script -and $script.ok) { Get-Sha256 $script.content } else { $null }
    }
    taskConfig = [ordered]@{
        url = $configUrl
        ok = $configResponse.ok
        status = $configResponse.status
        redacted = if ($configData) { Redact-Config $configData } else { $null }
    }
    uidInviteFlag = [ordered]@{
        url = $enableResponse.uri
        ok = $enableResponse.ok
        status = $enableResponse.status
        value = if ($enableResponse.ok) { $enableResponse.content.Trim() } else { $null }
    }
    discoveredEndpointPatterns = $endpointPatterns
    bundleFeatureEvidence = if ($script -and $script.ok) {
        [ordered]@{
            taskConfigRead = $script.content.Contains('/gjld/task/config?tid=')
            customerCaptchaLogin = $script.content.Contains('/captcha/login')
            orderConfirmation = $script.content.Contains('/gjld/user/confirm')
            workerSmsFlow = $script.content.Contains('/gjld/captcha/sendCode')
            workerSessionFlow = $script.content.Contains('/gjld/captcha/i/')
            profileStream = $script.content.Contains('/gjld/profile/stream')
            profileFallback = $script.content.Contains('/gjld/profile')
            authenticationFields = $script.content.Contains('isFirstAuth') -and $script.content.Contains('isSystem')
            browserTokenStorageObserved = $script.content.Contains('localStorage.setItem("sToken"')
            countFormulaObserved = $script.content.Contains('w.data.needNum-w.data.regNum')
        }
    } else { $null }
}

$evidencePath = Join-Path $OutputDirectory 'read-only-probe.json'
$evidence | ConvertTo-Json -Depth 8 | Set-Content -Path $evidencePath -Encoding UTF8

Write-Host "Read-only probe complete: $evidencePath"
Write-Host "Discovered endpoint patterns: $($endpointPatterns.Count)"
Write-Host 'No SMS, OTP, CAPTCHA, order, or payment action was performed.'

[CmdletBinding()]
param(
    [string]$Root = ''
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($Root)) {
    $Root = Split-Path -Parent $MyInvocation.MyCommand.Path
}

$allowedExtensions = @('.md', '.json')
$files = Get-ChildItem -Path $Root -Recurse -File | Where-Object {
    $allowedExtensions -contains $_.Extension.ToLowerInvariant()
}

$findings = [System.Collections.Generic.List[object]]::new()
foreach ($file in $files) {
    $text = Get-Content -Raw -Encoding UTF8 -LiteralPath $file.FullName

    foreach ($match in [regex]::Matches($text, '(?<!\d)1[3-9]\d{9}(?!\d)')) {
        $findings.Add([ordered]@{
            file = $file.FullName
            type = 'mainland-phone-number'
            offset = $match.Index
        })
    }

    foreach ($match in [regex]::Matches($text, '(?i)bearer\s+[a-z0-9._~-]{16,}')) {
        $findings.Add([ordered]@{
            file = $file.FullName
            type = 'bearer-token-like-value'
            offset = $match.Index
        })
    }

    foreach ($match in [regex]::Matches($text, '(?i)["'']?(?:otp|code|stoken|session[_ -]?token)["'']?\s*[=:]\s*["''][a-z0-9._~-]{12,}["'']')) {
        $value = $match.Value
        if ($value -notmatch '(?i)(synthetic|placeholder|example|<.*>)') {
            $findings.Add([ordered]@{
                file = $file.FullName
                type = 'credential-like-value'
                offset = $match.Index
            })
        }
    }
}

if ($findings.Count -gt 0) {
    $findings | ConvertTo-Json -Depth 4 | Write-Error
    throw "Sensitive-output scan found $($findings.Count) possible value(s)."
}

Write-Host "Sensitive-output scan passed for $($files.Count) Markdown/JSON files."

[CmdletBinding()]
param(
    [string]$OutputDirectory = ''
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
    $OutputDirectory = Join-Path $scriptDirectory 'evidence'
}

function Assert-Equal {
    param(
        [Parameter(Mandatory)]$Actual,
        [Parameter(Mandatory)]$Expected,
        [Parameter(Mandatory)][string]$Name
    )
    if ($Actual -ne $Expected) {
        throw "$Name failed: expected '$Expected', got '$Actual'"
    }
}

function New-OrderState {
    param([Parameter(Mandatory)][int]$Capacity, [datetime]$Now)
    [ordered]@{
        capacity = $Capacity
        openedAt = $Now
        expiresAt = $Now.AddHours(24)
        claims = @{}
        winners = @{}
    }
}

function Remove-ExpiredClaims {
    param($State, [datetime]$Now)
    foreach ($key in @($State.claims.Keys)) {
        if ($State.claims[$key].expiresAt -le $Now) {
            $State.claims.Remove($key)
        }
    }
}

function Get-ReservedCount {
    param($State, [datetime]$Now)
    Remove-ExpiredClaims $State $Now
    @($State.claims.Keys).Count
}

function Try-Claim {
    param($State, [string]$WorkerId, [datetime]$Now)
    if ($Now -ge $State.expiresAt) { return $false }
    if ($State.winners.ContainsKey($WorkerId) -or $State.claims.ContainsKey($WorkerId)) { return $false }
    Remove-ExpiredClaims $State $Now
    $available = $State.capacity - @($State.winners.Keys).Count - @($State.claims.Keys).Count
    if ($available -le 0) { return $false }
    $State.claims[$WorkerId] = [ordered]@{ claimedAt = $Now; expiresAt = $Now.AddMinutes(30) }
    return $true
}

function Try-Complete {
    param($State, [string]$WorkerId, [datetime]$Now)
    if ($Now -ge $State.expiresAt) { return $false }
    if ($State.winners.ContainsKey($WorkerId)) { return $false }
    Remove-ExpiredClaims $State $Now

    if ($State.claims.ContainsKey($WorkerId)) {
        $State.claims.Remove($WorkerId)
        $State.winners[$WorkerId] = [ordered]@{ completedAt = $Now; source = 'protected-claim' }
        return $true
    }

    # A timed-out worker may complete only when no winner or active claim owns
    # the remaining capacity.
    $available = $State.capacity - @($State.winners.Keys).Count - @($State.claims.Keys).Count
    if ($available -le 0) { return $false }
    $State.winners[$WorkerId] = [ordered]@{ completedAt = $Now; source = 'late-completion' }
    return $true
}

$start = [datetime]'2026-08-14T00:00:00Z'
$results = [System.Collections.Generic.List[object]]::new()

# Capacity protection and no overbooking.
$s1 = New-OrderState -Capacity 1 -Now $start
Assert-Equal (Try-Claim $s1 'A' $start) $true 'first claim accepted'
Assert-Equal (Try-Claim $s1 'B' $start) $false 'second claim rejected while protected'
Assert-Equal (Try-Complete $s1 'A' $start.AddMinutes(20)) $true 'protected worker completes'
Assert-Equal @($s1.winners.Keys).Count 1 'one winner only'
$results.Add([ordered]@{ scenario='capacity-protection'; passed=$true })

# Timeout releases the slot.
$s2 = New-OrderState -Capacity 1 -Now $start
[void](Try-Claim $s2 'A' $start)
Assert-Equal (Try-Claim $s2 'B' $start.AddMinutes(31)) $true 'slot released after timeout'
Assert-Equal (Try-Complete $s2 'A' $start.AddMinutes(32)) $false 'late worker cannot displace active claim'
Assert-Equal (Try-Complete $s2 'B' $start.AddMinutes(40)) $true 'replacement completes'
$results.Add([ordered]@{ scenario='timeout-release-and-protection'; passed=$true })

# Late completion is accepted when capacity remains free.
$s3 = New-OrderState -Capacity 2 -Now $start
[void](Try-Claim $s3 'A' $start)
[void](Try-Claim $s3 'B' $start)
[void](Try-Complete $s3 'A' $start.AddMinutes(10))
Assert-Equal (Try-Complete $s3 'B' $start.AddMinutes(31)) $true 'late completion uses free capacity'
Assert-Equal @($s3.winners.Keys).Count 2 'late completion capped at N'
$results.Add([ordered]@{ scenario='late-completion-while-open'; passed=$true })

# Order expiry closes claims and completions.
$s4 = New-OrderState -Capacity 10 -Now $start
Assert-Equal (Try-Claim $s4 'A' $start.AddHours(24)) $false 'claim rejected at order expiry'
Assert-Equal (Try-Complete $s4 'A' $start.AddHours(24)) $false 'completion rejected at order expiry'
$results.Add([ordered]@{ scenario='24-hour-expiry'; passed=$true })

# Idempotent completion.
$s5 = New-OrderState -Capacity 1 -Now $start
[void](Try-Claim $s5 'A' $start)
Assert-Equal (Try-Complete $s5 'A' $start.AddMinutes(1)) $true 'first completion accepted'
Assert-Equal (Try-Complete $s5 'A' $start.AddMinutes(2)) $false 'duplicate completion rejected'
Assert-Equal @($s5.winners.Keys).Count 1 'duplicate does not increase winners'
$results.Add([ordered]@{ scenario='idempotent-completion'; passed=$true })

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$resultPath = Join-Path $OutputDirectory 'task-rule-tests.json'
[ordered]@{
    generatedAt = (Get-Date).ToUniversalTime().ToString('o')
    passed = $true
    scenarios = $results
} | ConvertTo-Json -Depth 6 | Set-Content -Path $resultPath -Encoding UTF8

Write-Host "All $($results.Count) task-rule scenarios passed: $resultPath"

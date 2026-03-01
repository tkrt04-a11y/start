$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$logDir = Join-Path $repoRoot "logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$promotedMinText = if ($env:PROMOTED_MIN_COUNT) { $env:PROMOTED_MIN_COUNT } else { "1" }
$promotedMin = 1
try {
    $promotedMin = [Math]::Max(0, [int]$promotedMinText)
} catch {
    $promotedMin = 1
}

$alertsMaxLinesText = if ($env:ALERTS_MAX_LINES) { $env:ALERTS_MAX_LINES } else { "500" }
$alertsMaxLines = 500
try {
    $alertsMaxLines = [Math]::Max(50, [int]$alertsMaxLinesText)
} catch {
    $alertsMaxLines = 500
}

$alertWebhookRetriesText = if ($env:ALERT_WEBHOOK_RETRIES) { $env:ALERT_WEBHOOK_RETRIES } else { "3" }
$alertWebhookRetries = 3
try {
    $alertWebhookRetries = [Math]::Max(1, [int]$alertWebhookRetriesText)
} catch {
    $alertWebhookRetries = 3
}

$alertWebhookBackoffSecText = if ($env:ALERT_WEBHOOK_BACKOFF_SEC) { $env:ALERT_WEBHOOK_BACKOFF_SEC } else { "1.0" }
$alertWebhookBackoffSec = 1.0
try {
    $alertWebhookBackoffSec = [Math]::Max(0.1, [double]$alertWebhookBackoffSecText)
} catch {
    $alertWebhookBackoffSec = 1.0
}

$alertDedupCooldownSecText = if ($env:ALERT_DEDUP_COOLDOWN_SEC) { $env:ALERT_DEDUP_COOLDOWN_SEC } else { "600" }
$alertDedupCooldownSec = 600
try {
    $alertDedupCooldownSec = [Math]::Max(0, [int]$alertDedupCooldownSecText)
} catch {
    $alertDedupCooldownSec = 600
}
$alertDedupStatePath = Join-Path $logDir "alert_dedup_state.json"

$alertWebhookFormatText = if ($env:ALERT_WEBHOOK_FORMAT) { $env:ALERT_WEBHOOK_FORMAT } else { "generic" }
$alertWebhookFormat = $alertWebhookFormatText.Trim().ToLowerInvariant()
$alertWebhookFormatInvalid = $false
if (@("generic", "slack", "teams") -notcontains $alertWebhookFormat) {
    $alertWebhookFormatInvalid = $true
    $alertWebhookFormat = "generic"
}

$alertFile = Join-Path $logDir "alerts.log"
if (Test-Path $alertFile) {
    $existing = Get-Content $alertFile
    if ($existing.Count -ge $alertsMaxLines) {
        $archive = Join-Path $logDir ("alerts-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
        Move-Item $alertFile $archive -Force
    }
}

function Get-Utf8NoBomEncoding {
    return New-Object System.Text.UTF8Encoding($false)
}

function Add-Utf8Lines {
    param(
        [string]$Path,
        [string[]]$Lines
    )
    $writer = New-Object System.IO.StreamWriter($Path, $true, (Get-Utf8NoBomEncoding))
    try {
        foreach ($entry in $Lines) {
            $writer.WriteLine($entry)
        }
    } finally {
        $writer.Dispose()
    }
}

function Set-Utf8Text {
    param(
        [string]$Path,
        [string]$Text
    )
    [System.IO.File]::WriteAllText($Path, $Text, (Get-Utf8NoBomEncoding))
}

function Test-AlertWebhookDispatch {
    param(
        [string]$Line
    )

    if ($alertDedupCooldownSec -le 0) {
        return $true
    }

    try {
        $dedupOutput = @(
            & python -m src.alert_dedup --state-path $alertDedupStatePath --line $Line --cooldown-sec $alertDedupCooldownSec 2>&1
        )
        if ($LASTEXITCODE -ne 0) {
            Add-Utf8Lines -Path $LogFile -Lines @("[$(Get-Date -Format s)] WARNING weekly pipeline: alert dedup helper failed (exit=$LASTEXITCODE). webhook send will proceed")
            return $true
        }

        $dedupText = ($dedupOutput | Out-String).Trim()
        if (-not $dedupText) {
            Add-Utf8Lines -Path $LogFile -Lines @("[$(Get-Date -Format s)] WARNING weekly pipeline: alert dedup helper returned empty output. webhook send will proceed")
            return $true
        }

        $dedupResult = $dedupText | ConvertFrom-Json
        if ($dedupResult.send) {
            return $true
        }

        $signatureText = ""
        if ($dedupResult.signature) {
            $signatureText = [string]$dedupResult.signature
        }
        Add-Utf8Lines -Path $LogFile -Lines @("[$(Get-Date -Format s)] INFO weekly pipeline: webhook duplicate suppressed within cooldown ($alertDedupCooldownSec sec, signature=$signatureText)")
        return $false
    } catch {
        Add-Utf8Lines -Path $LogFile -Lines @("[$(Get-Date -Format s)] WARNING weekly pipeline: alert dedup helper error: $($_.Exception.Message). webhook send will proceed")
        return $true
    }
}

function Write-Alert {
    param(
        [string]$Line,
        [string]$WebhookUrl,
        [string]$LogFile,
        [string]$AlertFile
    )
    Add-Utf8Lines -Path $LogFile -Lines @($Line)
    Add-Utf8Lines -Path $AlertFile -Lines @($Line)

    $shouldSendWebhook = $true
    if ($WebhookUrl) {
        $shouldSendWebhook = Test-AlertWebhookDispatch -Line $Line
    }

    if ($WebhookUrl -and $shouldSendWebhook) {
        $payloadObject = $null
        switch ($alertWebhookFormat) {
            "slack" {
                $payloadObject = @{
                    text = $Line
                }
            }
            "teams" {
                $payloadObject = @{
                    '@type' = "MessageCard"
                    '@context' = "http://schema.org/extensions"
                    summary = $Line
                    text = $Line
                }
            }
            default {
                $payloadObject = @{
                    text = $Line
                    severity = "warning"
                    pipeline = "weekly"
                    event = "promoted_threshold"
                    timestamp = (Get-Date -Format s)
                }
            }
        }
        $payload = $payloadObject | ConvertTo-Json

        for ($attempt = 1; $attempt -le $alertWebhookRetries; $attempt++) {
            try {
                Add-Utf8Lines -Path $LogFile -Lines @("[$(Get-Date -Format s)] INFO weekly pipeline: alert webhook attempt $attempt/$alertWebhookRetries")
                Invoke-RestMethod -Method Post -Uri $WebhookUrl -ContentType "application/json" -Body $payload | Out-Null
                Add-Utf8Lines -Path $LogFile -Lines @("[$(Get-Date -Format s)] INFO weekly pipeline: alert webhook sent (attempt $attempt/$alertWebhookRetries)")
                break
            } catch {
                if ($attempt -lt $alertWebhookRetries) {
                    $sleepSec = [Math]::Round($alertWebhookBackoffSec * [Math]::Pow(2, $attempt - 1), 3)
                    Add-Utf8Lines -Path $LogFile -Lines @("[$(Get-Date -Format s)] WARNING weekly pipeline: alert webhook attempt $attempt/$alertWebhookRetries failed: $($_.Exception.Message). retrying in $sleepSec sec")
                    Start-Sleep -Seconds $sleepSec
                } else {
                    Add-Utf8Lines -Path $LogFile -Lines @("[$(Get-Date -Format s)] ERROR weekly pipeline: alert webhook final failure after $alertWebhookRetries attempts: $($_.Exception.Message)")
                }
            }
        }
    }
}

$envFile = Join-Path $repoRoot ".env"
if ((-not $env:OPENAI_API_KEY) -and (Test-Path $envFile)) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        $parts = $line -split "=", 2
        if ($parts.Length -eq 2) {
            $name = $parts[0].Trim()
            $value = $parts[1].Trim().Trim('"')
            if ($name -eq "OPENAI_API_KEY" -and $value) {
                $env:OPENAI_API_KEY = $value
            }
        }
    }
}

$logFile = Join-Path $logDir ("weekly-run-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
$pipelineStartedAt = Get-Date
$pipelineStartedAtText = $pipelineStartedAt.ToString("o")

$monthlyReportCommand = $null
$monthlyReportTarget = $null
$today = Get-Date
if ($today.Day -eq 1) {
    $monthlyReportTarget = $today.AddMonths(-1).ToString("yyyy-MM")
    $monthlyReportCommand = "python -m src.main monthly-report --month $monthlyReportTarget --ai"
}

$metricsCheckCommand = "python -m src.main metrics-check --days 30"

$commands = @(
    "python -m src.main analyze --ai",
    "python -m src.main apply-insights --ai",
    "python -m src.main weekly-report --ai",
    $metricsCheckCommand,
    "python -m src.main ops-report --days 7",
    "python -m src.main ops-report-index --limit 8",
    "python -m src.main retention"
)

Add-Utf8Lines -Path $logFile -Lines @("=== Weekly pipeline started: $(Get-Date -Format s) ===")
if ($alertWebhookFormatInvalid) {
    Add-Utf8Lines -Path $logFile -Lines @("[$(Get-Date -Format s)] WARNING weekly pipeline: invalid ALERT_WEBHOOK_FORMAT '$alertWebhookFormatText'. using 'generic'")
}
if ($monthlyReportCommand) {
    $commands += $monthlyReportCommand
    $monthlyLine = "[$(Get-Date -Format s)] INFO weekly pipeline: monthly report scheduled for $monthlyReportTarget"
    Add-Utf8Lines -Path $logFile -Lines @($monthlyLine)
    Add-Utf8Lines -Path $alertFile -Lines @($monthlyLine)
}
Add-Utf8Lines -Path $logFile -Lines @("[$(Get-Date -Format s)] INFO weekly pipeline: alert webhook format=$alertWebhookFormat")
Add-Utf8Lines -Path $logFile -Lines @("[$(Get-Date -Format s)] INFO weekly pipeline: alert dedup cooldown sec=$alertDedupCooldownSec state=$alertDedupStatePath")
$commandFailures = 0
$runAlerts = New-Object System.Collections.Generic.List[string]
$promotedDetected = $null
foreach ($cmd in $commands) {
    Add-Utf8Lines -Path $logFile -Lines @("", ">>> $cmd")
    try {
        $cmdOutputLines = Invoke-Expression $cmd 2>&1 | ForEach-Object {
            $line = [string]$_
            Add-Utf8Lines -Path $logFile -Lines @($line)
            $line
        }
        $cmdOutput = $cmdOutputLines | Out-String
        $cmdExitCode = $LASTEXITCODE
    } catch {
        $commandFailures += 1
        $failureLine = "[$(Get-Date -Format s)] ERROR weekly pipeline: command failed: $cmd"
        Add-Utf8Lines -Path $logFile -Lines @($failureLine)
        continue
    }

    if ($cmd -eq "python -m src.main apply-insights --ai") {
        $promotedCount = $null
        $match = [regex]::Match($cmdOutput, "Synced Promoted actions:\s*(\d+)")
        if ($match.Success) {
            $promotedCount = [int]$match.Groups[1].Value
            $promotedDetected = $promotedCount
        }
        if ($null -ne $promotedCount -and $promotedCount -lt $promotedMin) {
            $alertLine = "[$(Get-Date -Format s)] WARNING weekly pipeline: promoted actions below threshold ($promotedCount < $promotedMin)"
            Write-Alert -Line $alertLine -WebhookUrl $env:ALERT_WEBHOOK_URL -LogFile $logFile -AlertFile $alertFile
            $runAlerts.Add($alertLine) | Out-Null
        }
    }

    if ($cmd -eq $metricsCheckCommand -and $cmdExitCode -ne 0) {
        $continuousAlertActive = $false
        $continuousMatch = [regex]::Match($cmdOutput, "Continuous SLO alert active:\s*(true|false)", [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if ($continuousMatch.Success) {
            $continuousAlertActive = $continuousMatch.Groups[1].Value.ToLowerInvariant() -eq "true"
        }

        if ($continuousAlertActive) {
            $alertLine = "[$(Get-Date -Format s)] WARNING weekly pipeline: metrics-check reported continuous SLO threshold violations"
            Write-Alert -Line $alertLine -WebhookUrl $env:ALERT_WEBHOOK_URL -LogFile $logFile -AlertFile $alertFile
            $runAlerts.Add($alertLine) | Out-Null
        } else {
            Add-Utf8Lines -Path $logFile -Lines @("[$(Get-Date -Format s)] INFO weekly pipeline: metrics-check violation detected but continuous alert condition not met")
        }
    }
}
Add-Utf8Lines -Path $logFile -Lines @("=== Weekly pipeline finished: $(Get-Date -Format s) ===")

$pipelineFinishedAt = Get-Date
$pipelineFinishedAtText = $pipelineFinishedAt.ToString("o")
$pipelineDurationSec = [Math]::Round(($pipelineFinishedAt - $pipelineStartedAt).TotalSeconds, 3)
$metricsPath = Join-Path $logDir ("weekly-metrics-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".json")
$metrics = [ordered]@{
    pipeline = "weekly"
    started_at = $pipelineStartedAtText
    finished_at = $pipelineFinishedAtText
    duration_sec = $pipelineDurationSec
    command_failures = $commandFailures
    alert_count = $runAlerts.Count
    promoted_threshold = $promotedMin
    promoted_detected = $promotedDetected
    monthly_report_target = $monthlyReportTarget
    webhook_format = $alertWebhookFormat
    success = ($commandFailures -eq 0)
}
Set-Utf8Text -Path $metricsPath -Text (($metrics | ConvertTo-Json -Depth 5) + "`n")

$summaryPath = Join-Path $logDir ("alerts-summary-" + (Get-Date -Format "yyyyMMdd") + "-weekly.md")
$summaryLines = @(
    "# Alert Summary (Weekly)",
    "",
    "Generated: $(Get-Date -Format s)",
    "- Command failures: $commandFailures",
    "- Alert count: $($runAlerts.Count)",
    ""
)
if ($runAlerts.Count -gt 0) {
    $summaryLines += "## Alerts"
    foreach ($line in $runAlerts) {
        $summaryLines += "- $line"
    }
}
Set-Utf8Text -Path $summaryPath -Text ($summaryLines -join "`n")

if ($commandFailures -gt 0) {
    exit 1
}

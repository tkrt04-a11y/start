param(
    [string]$TaskName = "AIStarterDailyPipeline",
    [string]$Time = "09:00",
    [switch]$DryRun,
    [switch]$ValidateOnly
)

$registerScript = Join-Path $PSScriptRoot "register_pipeline_tasks.ps1"
if (-not (Test-Path $registerScript)) {
    throw "register_pipeline_tasks.ps1 was not found: $registerScript"
}

$registerParams = @{
    Pipelines = @("daily")
    DailyTaskName = $TaskName
    DailyTime = $Time
}

if ($DryRun) {
    $registerParams.DryRun = $true
}

if ($ValidateOnly) {
    $registerParams.ValidateOnly = $true
}

& $registerScript @registerParams

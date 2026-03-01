param(
    [string]$TaskName = "AIStarterWeeklyPipeline",
    [string]$Day = "SUN",
    [string]$Time = "09:30",
    [switch]$DryRun,
    [switch]$ValidateOnly
)

$registerScript = Join-Path $PSScriptRoot "register_pipeline_tasks.ps1"
if (-not (Test-Path $registerScript)) {
    throw "register_pipeline_tasks.ps1 was not found: $registerScript"
}

$registerParams = @{
    Pipelines = @("weekly")
    WeeklyTaskName = $TaskName
    WeeklyDay = $Day
    WeeklyTime = $Time
}

if ($DryRun) {
    $registerParams.DryRun = $true
}

if ($ValidateOnly) {
    $registerParams.ValidateOnly = $true
}

& $registerScript @registerParams

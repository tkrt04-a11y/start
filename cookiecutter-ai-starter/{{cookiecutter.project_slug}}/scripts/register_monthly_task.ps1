param(
    [string]$TaskName = "AIStarterMonthlyPipeline",
    [int]$Day = 1,
    [string]$Time = "10:00",
    [switch]$DryRun,
    [switch]$ValidateOnly
)

$registerScript = Join-Path $PSScriptRoot "register_pipeline_tasks.ps1"
if (-not (Test-Path $registerScript)) {
    throw "register_pipeline_tasks.ps1 was not found: $registerScript"
}

$registerParams = @{
    Pipelines = @("monthly")
    MonthlyTaskName = $TaskName
    MonthlyDay = $Day
    MonthlyTime = $Time
}

if ($DryRun) {
    $registerParams.DryRun = $true
}

if ($ValidateOnly) {
    $registerParams.ValidateOnly = $true
}

& $registerScript @registerParams

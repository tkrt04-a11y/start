param(
    [string]$DailyTaskName = "AIStarterDailyPipeline",
    [string]$DailyTime = "09:00",
    [string]$WeeklyTaskName = "AIStarterWeeklyPipeline",
    [string]$WeeklyDay = "SUN",
    [string]$WeeklyTime = "09:30",
    [string]$MonthlyTaskName = "AIStarterMonthlyPipeline",
    [int]$MonthlyDay = 1,
    [string]$MonthlyTime = "10:00",
    [string[]]$Pipelines = @("daily", "weekly", "monthly"),
    [switch]$DryRun,
    [switch]$ValidateOnly
)

$normalizedPipelines = @(
    $Pipelines |
        ForEach-Object { $_ -split "," } |
        ForEach-Object { $_.ToLowerInvariant().Trim() } |
        Where-Object { $_ -ne "" } |
        Select-Object -Unique
)
if ($normalizedPipelines.Count -eq 0) {
    throw "Pipelines must include at least one of: daily, weekly, monthly"
}

$allowedPipelines = @("daily", "weekly", "monthly")
$unknownPipelines = @($normalizedPipelines | Where-Object { $_ -notin $allowedPipelines })
if ($unknownPipelines.Count -gt 0) {
    throw "Unknown pipeline(s): $($unknownPipelines -join ', '). Allowed values: daily, weekly, monthly"
}

function Test-RegistrationInputs {
    param(
        [string[]]$SelectedPipelines,
        [string]$ScriptRoot,
        [string]$DailyTimeValue,
        [string]$WeeklyDayValue,
        [string]$WeeklyTimeValue,
        [int]$MonthlyDayValue,
        [string]$MonthlyTimeValue
    )

    $errors = New-Object System.Collections.Generic.List[string]
    $allowedDays = @("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
    $timePattern = '^([01]\d|2[0-3]):[0-5]\d$'

    foreach ($pipelineName in $SelectedPipelines) {
        $expectedScript = Join-Path $ScriptRoot ("{0}_pipeline.ps1" -f $pipelineName)
        if (-not (Test-Path $expectedScript)) {
            $errors.Add("${pipelineName}_pipeline.ps1 was not found: $expectedScript")
        }
    }

    if ($SelectedPipelines -contains "daily") {
        if ($DailyTimeValue -notmatch $timePattern) {
            $errors.Add("DailyTime must be HH:mm (24-hour), got '$DailyTimeValue'.")
        }
    }

    if ($SelectedPipelines -contains "weekly") {
        if ($WeeklyTimeValue -notmatch $timePattern) {
            $errors.Add("WeeklyTime must be HH:mm (24-hour), got '$WeeklyTimeValue'.")
        }

        $normalizedDay = $WeeklyDayValue.ToUpperInvariant().Trim()
        if ($normalizedDay -notin $allowedDays) {
            $errors.Add("WeeklyDay must be one of MON,TUE,WED,THU,FRI,SAT,SUN, got '$WeeklyDayValue'.")
        }
    }

    if ($SelectedPipelines -contains "monthly") {
        if ($MonthlyTimeValue -notmatch $timePattern) {
            $errors.Add("MonthlyTime must be HH:mm (24-hour), got '$MonthlyTimeValue'.")
        }

        if ($MonthlyDayValue -lt 1 -or $MonthlyDayValue -gt 31) {
            $errors.Add("MonthlyDay must be between 1 and 31, got '$MonthlyDayValue'.")
        }
    }

    return $errors
}

$validationErrors = Test-RegistrationInputs `
    -SelectedPipelines $normalizedPipelines `
    -ScriptRoot $PSScriptRoot `
    -DailyTimeValue $DailyTime `
    -WeeklyDayValue $WeeklyDay `
    -WeeklyTimeValue $WeeklyTime `
    -MonthlyDayValue $MonthlyDay `
    -MonthlyTimeValue $MonthlyTime

if ($ValidateOnly) {
    if ($validationErrors.Count -eq 0) {
        Write-Output "Validation succeeded."
        Write-Output ("Pipelines: {0}" -f ($normalizedPipelines -join ", "))
        exit 0
    }

    Write-Output "Validation failed:"
    $validationErrors | ForEach-Object { Write-Output ("- {0}" -f $_) }
    exit 1
}

$registered = @()

foreach ($pipeline in $normalizedPipelines) {
    $scriptPath = Join-Path $PSScriptRoot ("{0}_pipeline.ps1" -f $pipeline)
    if (-not (Test-Path $scriptPath)) {
        throw "${pipeline}_pipeline.ps1 was not found: $scriptPath"
    }

    $action = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

    if ($pipeline -eq "daily") {
        if ($DryRun) {
            Write-Output ("[DryRun] schtasks /Create /F /SC DAILY /ST {0} /TN {1} /TR {2}" -f $DailyTime, $DailyTaskName, $action)
        }
        else {
            schtasks /Create /F /SC DAILY /ST $DailyTime /TN $DailyTaskName /TR $action
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to register daily scheduled task."
            }
        }

        $registered += [PSCustomObject]@{
            Pipeline = "daily"
            TaskName = $DailyTaskName
            Schedule = "DAILY $DailyTime"
        }
        continue
    }

    if ($pipeline -eq "weekly") {
        if ($DryRun) {
            Write-Output ("[DryRun] schtasks /Create /F /SC WEEKLY /D {0} /ST {1} /TN {2} /TR {3}" -f $WeeklyDay, $WeeklyTime, $WeeklyTaskName, $action)
        }
        else {
            schtasks /Create /F /SC WEEKLY /D $WeeklyDay /ST $WeeklyTime /TN $WeeklyTaskName /TR $action
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to register weekly scheduled task."
            }
        }

        $registered += [PSCustomObject]@{
            Pipeline = "weekly"
            TaskName = $WeeklyTaskName
            Schedule = "WEEKLY $WeeklyDay $WeeklyTime"
        }
        continue
    }

    if ($DryRun) {
        Write-Output ("[DryRun] schtasks /Create /F /SC MONTHLY /D {0} /ST {1} /TN {2} /TR {3}" -f $MonthlyDay, $MonthlyTime, $MonthlyTaskName, $action)
    }
    else {
        schtasks /Create /F /SC MONTHLY /D $MonthlyDay /ST $MonthlyTime /TN $MonthlyTaskName /TR $action
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to register monthly scheduled task."
        }
    }

    $registered += [PSCustomObject]@{
        Pipeline = "monthly"
        TaskName = $MonthlyTaskName
        Schedule = "MONTHLY day $MonthlyDay $MonthlyTime"
    }
}

if ($DryRun) {
    Write-Output "Dry-run summary:"
}
else {
    Write-Output "Registered tasks summary:"
}

$registered | ForEach-Object {
    Write-Output ("- {0}: {1} ({2})" -f $_.Pipeline, $_.TaskName, $_.Schedule)
}
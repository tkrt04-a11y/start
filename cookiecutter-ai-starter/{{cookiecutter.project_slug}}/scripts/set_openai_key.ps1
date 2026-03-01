param(
    [switch]$Machine
)

$secureKey = Read-Host "Enter OPENAI_API_KEY" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}

if (-not $plainKey -or -not $plainKey.StartsWith("sk-")) {
    throw "OPENAI_API_KEY format looks invalid."
}

$target = if ($Machine) { "Machine" } else { "User" }
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", $plainKey, $target)
$env:OPENAI_API_KEY = $plainKey

Write-Output "OPENAI_API_KEY saved to $target environment."
Write-Output "Current terminal updated too."
Write-Output "Verify: python -m src.main analyze --ai"

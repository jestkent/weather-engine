# Wrapper invoked by the Windows Scheduled Task. Resolves the project root from its own
# location so it works no matter where the repo lives, then launches the 24/7 collector.
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot   # deploy\ -> project root
Set-Location $proj

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py run_forever.py
} else {
    & python run_forever.py
}

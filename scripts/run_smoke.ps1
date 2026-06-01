# Smoke test for ArionAgent (wait for slow first-time scipy/scml import)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$here = Split-Path $PSScriptRoot -Parent

$venvPy = "c:\OZU-MS\Introduction to AI\Project\scml_resources\std_local\.venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $py = $venvPy
    Write-Host "Using course venv: $py"
} else {
    $py = "python"
    Write-Host "Using default python (first run may take 1-2 min to load scipy)..."
}

Set-Location $here
& $py -m arion_strategists.helpers.runner smoke-all 5 1

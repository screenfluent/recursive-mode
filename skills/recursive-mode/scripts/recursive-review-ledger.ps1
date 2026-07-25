[CmdletBinding(DefaultParameterSetName = "Run")]
param(
    [string]$RepoRoot = (Get-Location).Path,
    [Parameter(Mandatory = $true, ParameterSetName = "Ledger")][string]$Ledger,
    [Parameter(Mandatory = $true, ParameterSetName = "Run")][AllowEmptyString()][string]$RunId,
    [Parameter(ParameterSetName = "Run")][string]$PhaseArtifact = "03.5-code-review.md"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$python = if ($env:PYTHON) { $env:PYTHON } elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { $null }
if (-not $python) {
    Write-Host "[FAIL] Python executable not found in PATH."
    exit 1
}

$argsList = @((Join-Path $PSScriptRoot "recursive-review-ledger.py"), "--repo-root", $RepoRoot)
if ($PSCmdlet.ParameterSetName -eq "Ledger") {
    $argsList += @("--ledger", $Ledger)
} else {
    $argsList += @("--run-id", $RunId, "--phase-artifact", $PhaseArtifact)
}

& $python @argsList
exit $LASTEXITCODE

#Requires -Version 5.1
<#
.SYNOPSIS
    Repository-local Training-Free GRPO for recursive-mode runs (PowerShell wrapper).

.DESCRIPTION
    Thin wrapper that calls recursive-training-grpo.py with the same arguments.
    Extraction is delegated to recursive-training-extract.py (response-file or
    RECURSIVE_TRAINING_EXTRACTOR_CMD). This wrapper does not select an LLM provider.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,

    [Parameter()]
    [switch]$Incremental,

    [Parameter()]
    [string]$RunId,

    [Parameter()]
    [int]$WinnerOnlyThreshold = 0
)

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command python3 -ErrorAction SilentlyContinue
}

if (-not $python) {
    Write-Error "Python is required but not found. Please install Python 3.10+."
    exit 1
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyScript = Join-Path $scriptDir "recursive-training-grpo.py"

$argsList = @("--repo-root", $RepoRoot)
if ($Incremental) {
    $argsList += "--incremental"
}
if ($RunId) {
    $argsList += @("--run-id", $RunId)
}
if ($WinnerOnlyThreshold -gt 0) {
    $argsList += @("--winner-only-threshold", "$WinnerOnlyThreshold")
}

& $python.Source $pyScript @argsList
exit $LASTEXITCODE

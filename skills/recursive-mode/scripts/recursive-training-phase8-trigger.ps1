#Requires -Version 5.1
<#
.SYNOPSIS
    Post-Phase 8 training trigger for recursive-mode.

.DESCRIPTION
    Thin wrapper around recursive-training-phase8-trigger.py.
    Extraction transport is owned by recursive-training-extract.py, not this wrapper.

.PARAMETER RepoRoot
    Path to the git repository root.

.PARAMETER RunId
    The run that just completed Phase 8.

.PARAMETER Auto
    Skip user confirmation and run training immediately.

.PARAMETER GrpoArgs
    Extra arguments passed through to recursive-training-grpo.py
    (for example: '--winner-only-threshold 3').

.EXAMPLE
    .\recursive-training-phase8-trigger.ps1 -RepoRoot . -RunId phase25 -Auto
#>
param(
    [Parameter(Mandatory)]
    [string]$RepoRoot,

    [Parameter(Mandatory)]
    [string]$RunId,

    [switch]$Auto,

    [string]$GrpoArgs = ""
)

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command python3 -ErrorAction SilentlyContinue
}
if (-not $python) {
    Write-Error "Python is required but not found."
    exit 1
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyScript = Join-Path $scriptDir "recursive-training-phase8-trigger.py"

$argsList = @("--repo-root", $RepoRoot, "--run-id", $RunId)
if ($Auto) { $argsList += "--auto" }
if ($GrpoArgs) { $argsList += @("--grpo-args", $GrpoArgs) }

& $python.Source $pyScript @argsList
exit $LASTEXITCODE

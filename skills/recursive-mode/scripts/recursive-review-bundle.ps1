[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][AllowEmptyString()][string]$RunId,
    [Parameter(Mandatory = $true)][string]$Phase,
    [Parameter(Mandatory = $true)][string]$Role,
    [Parameter(Mandatory = $true)][string]$ArtifactPath,
    [string]$RepoRoot = (Get-Location).Path,
    [string[]]$UpstreamArtifact = @(),
    [string[]]$Addendum = @(),
    [string[]]$PriorRef = @(),
    [string[]]$ControlDoc = @(),
    [string[]]$CodeRef = @(),
    [string[]]$EvidenceRef = @(),
    [string[]]$AuditQuestion = @(),
    [string]$ReviewId = "",
    [Parameter(Mandatory = $true)][string]$ReviewPass,
    [string]$RoutingConfigPath = "",
    [string]$RoutingDiscoveryPath = "",
    [string]$RoutedCli = "",
    [string]$RoutedModel = "",
    [switch]$NoAutoAddenda
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$python = if ($env:PYTHON) { $env:PYTHON } elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { $null }
if (-not $python) {
    Write-Host "[FAIL] Python executable not found in PATH."
    exit 1
}

$scriptPath = Join-Path $PSScriptRoot "recursive-review-bundle.py"
$argsList = @(
    $scriptPath,
    "--repo-root", $RepoRoot,
    "--run-id", $RunId,
    "--phase", $Phase,
    "--role", $Role,
    "--artifact-path", $ArtifactPath
)
if ($ReviewId) { $argsList += @("--review-id", $ReviewId) }
$argsList += @("--pass", $ReviewPass)
if ($NoAutoAddenda.IsPresent) { $argsList += "--no-auto-addenda" }
foreach ($value in @($UpstreamArtifact)) { if (-not [string]::IsNullOrWhiteSpace($value)) { $argsList += @("--upstream-artifact", $value) } }
foreach ($value in @($Addendum)) { if (-not [string]::IsNullOrWhiteSpace($value)) { $argsList += @("--addendum", $value) } }
foreach ($value in @($PriorRef)) { if (-not [string]::IsNullOrWhiteSpace($value)) { $argsList += @("--prior-ref", $value) } }
foreach ($value in @($ControlDoc)) { if (-not [string]::IsNullOrWhiteSpace($value)) { $argsList += @("--control-doc", $value) } }
foreach ($value in @($CodeRef)) { if (-not [string]::IsNullOrWhiteSpace($value)) { $argsList += @("--code-ref", $value) } }
foreach ($value in @($EvidenceRef)) { if (-not [string]::IsNullOrWhiteSpace($value)) { $argsList += @("--evidence-ref", $value) } }
foreach ($value in @($AuditQuestion)) { if (-not [string]::IsNullOrWhiteSpace($value)) { $argsList += @("--audit-question", $value) } }
if ($RoutingConfigPath) { $argsList += @("--routing-config-path", $RoutingConfigPath) }
if ($RoutingDiscoveryPath) { $argsList += @("--routing-discovery-path", $RoutingDiscoveryPath) }
if ($RoutedCli) { $argsList += @("--routed-cli", $RoutedCli) }
if ($RoutedModel) { $argsList += @("--routed-model", $RoutedModel) }

& $python @argsList
exit $LASTEXITCODE

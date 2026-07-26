[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][AllowEmptyString()][string]$RunId,
    [Parameter(Mandatory = $true)][string]$SubagentId,
    [Parameter(Mandatory = $true)][string]$Phase,
    [Parameter(Mandatory = $true)][string]$Purpose,
    [Parameter(Mandatory = $true)][string]$ExecutionMode,
    [string]$ArtifactPath = "",
    [string]$RepoRoot = (Get-Location).Path,
    [string[]]$UpstreamArtifact = @(),
    [string[]]$Addendum = @(),
    [string]$ReviewBundle = "",
    [string]$DiffBasis = "",
    [string[]]$CodeRef = @(),
    [string[]]$MemoryRef = @(),
    [string[]]$AuditQuestion = @(),
    [string[]]$ActionTaken = @(),
    [string[]]$CreatedFile = @(),
    [string[]]$ModifiedFile = @(),
    [string[]]$ReviewedFile = @(),
    [string[]]$UntouchedFile = @(),
    [string[]]$ArtifactRead = @(),
    [string[]]$ArtifactUpdated = @(),
    [string[]]$EvidenceUsed = @(),
    [string]$ReviewLedger = "",
    [string[]]$FindingClaim = @(),
    [string[]]$FindingChange = @(),
    [string[]]$FindingVerification = @(),
    [string[]]$Finding = @(),
    [string[]]$VerificationPath = @(),
    [string[]]$VerificationItem = @(),
    [string]$RouterUsed = "",
    [string]$RoutedRole = "",
    [string]$RoutedCli = "",
    [string]$RoutedModel = "",
    [string]$RoutingConfigPath = "",
    [string]$RoutingDiscoveryPath = "",
    [string]$RoutingResolutionBasis = "",
    [string]$RoutingFallbackReason = "",
    [string]$CliProbeSummary = "",
    [string]$PromptBundlePath = "",
    [string]$InvocationExitCode = "",
    [string[]]$OutputCapturePath = @(),
    [string]$OutputName = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$python = if ($env:PYTHON) { $env:PYTHON } elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { $null }
if (-not $python) {
    Write-Host "[FAIL] Python executable not found in PATH."
    exit 1
}

$scriptPath = Join-Path $PSScriptRoot "recursive-subagent-action.py"
$argsList = @(
    $scriptPath,
    "--repo-root", $RepoRoot,
    "--run-id", $RunId,
    "--subagent-id", $SubagentId,
    "--phase", $Phase,
    "--purpose", $Purpose,
    "--execution-mode", $ExecutionMode
)

if ($ArtifactPath) { $argsList += @("--artifact-path", $ArtifactPath) }
if ($ReviewBundle) { $argsList += @("--review-bundle", $ReviewBundle) }
if ($ReviewLedger) { $argsList += @("--review-ledger", $ReviewLedger) }
if ($DiffBasis) { $argsList += @("--diff-basis", $DiffBasis) }
if ($OutputName) { $argsList += @("--output-name", $OutputName) }
if ($RouterUsed) { $argsList += @("--router-used", $RouterUsed) }
if ($RoutedRole) { $argsList += @("--routed-role", $RoutedRole) }
if ($RoutedCli) { $argsList += @("--routed-cli", $RoutedCli) }
if ($RoutedModel) { $argsList += @("--routed-model", $RoutedModel) }
if ($RoutingConfigPath) { $argsList += @("--routing-config-path", $RoutingConfigPath) }
if ($RoutingDiscoveryPath) { $argsList += @("--routing-discovery-path", $RoutingDiscoveryPath) }
if ($RoutingResolutionBasis) { $argsList += @("--routing-resolution-basis", $RoutingResolutionBasis) }
if ($RoutingFallbackReason) { $argsList += @("--routing-fallback-reason", $RoutingFallbackReason) }
if ($CliProbeSummary) { $argsList += @("--cli-probe-summary", $CliProbeSummary) }
if ($PromptBundlePath) { $argsList += @("--prompt-bundle-path", $PromptBundlePath) }
if ($InvocationExitCode) { $argsList += @("--invocation-exit-code", $InvocationExitCode) }

foreach ($value in @($UpstreamArtifact)) { $argsList += @("--upstream-artifact", $value) }
foreach ($value in @($Addendum)) { $argsList += @("--addendum", $value) }
foreach ($value in @($CodeRef)) { $argsList += @("--code-ref", $value) }
foreach ($value in @($MemoryRef)) { $argsList += @("--memory-ref", $value) }
foreach ($value in @($AuditQuestion)) { if ($value.Trim()) { $argsList += @("--audit-question", $value.Trim()) } }
foreach ($value in @($ActionTaken)) { if ($value.Trim()) { $argsList += @("--action-taken", $value.Trim()) } }
foreach ($value in @($CreatedFile)) { $argsList += @("--created-file", $value) }
foreach ($value in @($ModifiedFile)) { $argsList += @("--modified-file", $value) }
foreach ($value in @($ReviewedFile)) { $argsList += @("--reviewed-file", $value) }
foreach ($value in @($UntouchedFile)) { $argsList += @("--untouched-file", $value) }
foreach ($value in @($ArtifactRead)) { $argsList += @("--artifact-read", $value) }
foreach ($value in @($ArtifactUpdated)) { $argsList += @("--artifact-updated", $value) }
foreach ($value in @($EvidenceUsed)) { $argsList += @("--evidence-used", $value) }
foreach ($value in @($FindingClaim)) { if ($value.Trim()) { $argsList += @("--finding-claim", $value.Trim()) } }
foreach ($value in @($FindingChange)) { $argsList += @("--finding-change", $value) }
foreach ($value in @($FindingVerification)) { if ($value.Trim()) { $argsList += @("--finding-verification", $value.Trim()) } }
foreach ($value in @($Finding)) { if ($value.Trim()) { $argsList += @("--finding", $value.Trim()) } }
foreach ($value in @($VerificationPath)) { $argsList += @("--verification-path", $value) }
foreach ($value in @($VerificationItem)) { if ($value.Trim()) { $argsList += @("--verification-item", $value.Trim()) } }
foreach ($value in @($OutputCapturePath)) { $argsList += @("--output-capture-path", $value) }

& $python @argsList
exit $LASTEXITCODE

param(
    [Parameter(Mandatory=$true)][string]$InputFile,
    [int]$ContextTokens = 0,
    [ValidateSet('auto','whole','context')][string]$Mode = 'auto',
    [int]$BatchSize = 8,
    [ValidateSet('qwen','gemma')][string]$Model = 'qwen',
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
if ($ContextTokens -eq 0) { $ContextTokens = if ($Model -eq 'gemma') { 8192 } else { 16384 } }
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectDir 'runtime\python\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Python is missing: $python" }
$script = Join-Path $projectDir 'translate.py'
$runnerArgs = @($script, $InputFile, '--context-tokens', [string]$ContextTokens, '--model-tag', $Model, '--mode', $Mode, '--batch-size', [string]$BatchSize)
if ($DryRun) { $runnerArgs += '--dry-run' }
& $python @runnerArgs
exit $LASTEXITCODE

param(
    [string[]]$Files,
    [string]$FileList,
    [ValidateSet('qwen','gemma')][string]$Model = 'qwen',
    [int]$ContextTokens = 0,
    [ValidateSet('auto','whole','context')][string]$Mode = 'auto',
    [int]$BatchSize = 8,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
if ($ContextTokens -eq 0) { $ContextTokens = if ($Model -eq 'gemma') { 8192 } else { 16384 } }
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $projectDir 'run-translate.ps1'
if ($FileList) {
    if (-not (Test-Path -LiteralPath $FileList)) { throw "File list not found: $FileList" }
    $Files = @(Get-Content -LiteralPath $FileList | ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') })
}
if (-not $Files) { throw 'Pass -Files or -FileList with explicitly selected strings.json paths.' }
foreach ($file in $Files) {
    if (-not (Test-Path -LiteralPath $file)) { throw "Input not found: $file" }
    Write-Host "Processing $file with $Model"
    & $runner -InputFile $file -Model $Model -ContextTokens $ContextTokens -Mode $Mode -BatchSize $BatchSize -DryRun:$DryRun
    if ($LASTEXITCODE -ne 0) { throw "Translation stopped at $file (exit $LASTEXITCODE)" }
}

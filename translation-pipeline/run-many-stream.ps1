param(
    [string[]]$Files,
    [string]$FileList,
    [ValidateSet('deepseek','qwen','gemma')][string]$Model = 'deepseek',
    [int]$ContextTokens = 0,
    [int]$GpuLayers = -1
)
$ErrorActionPreference = 'Stop'
if ($FileList) {
    if (-not (Test-Path -LiteralPath $FileList)) { throw "File list not found: $FileList" }
    $Files = @(Get-Content -LiteralPath $FileList | ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and -not $_.StartsWith('#') })
}
if (-not $Files) { throw 'Pass -Files or -FileList with selected strings.json paths.' }
$runner = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'run-stream.ps1'
foreach ($file in $Files) {
    if (-not (Test-Path -LiteralPath $file)) { throw "Input not found: $file" }
    Write-Host "Processing $file with $Model"
    & $runner -InputFile $file -Model $Model -ContextTokens $ContextTokens -GpuLayers $GpuLayers
    if ($LASTEXITCODE -ne 0) { throw "Translation stopped at $file (exit $LASTEXITCODE)" }
}

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
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectDir 'runtime\python\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Python is missing: $python" }
$models = @{
    deepseek = 'F:\Models\DeepSeek-V4-Flash-0731-UD-Q3_K_M-00001-of-00004.gguf'
    qwen = (Join-Path $projectDir 'models\Qwen3.8-27B-Q4_K_M.gguf')
    gemma = (Join-Path $projectDir 'models\gemma-4-31B-it-QAT-Q4_0.gguf')
}
if ($ContextTokens -eq 0) { $ContextTokens = if ($Model -eq 'deepseek') { 262144 } else { 16384 } }
$modelPath = $models[$Model]
if (-not (Test-Path -LiteralPath $modelPath)) { throw "Model is missing: $modelPath" }
$resolvedFiles = @($Files | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_ -PathType Leaf)) { throw "Input not found: $_" }
    (Resolve-Path -LiteralPath $_).ProviderPath
})
$runnerArgs = @(
    (Join-Path $projectDir 'translate_stream.py'), '--batch-from-env',
    '--model', $modelPath, '--model-tag', $Model,
    '--context-tokens', [string]$ContextTokens
)
if ($GpuLayers -ge 0) { $runnerArgs += @('--gpu-layers', [string]$GpuLayers) }

$savedEnv = @{}
try {
    $names = @('TRANSLATE_DROP_COUNT') + @(1..$resolvedFiles.Count | ForEach-Object { "TRANSLATE_DROP_$_" })
    foreach ($name in $names) {
        $savedEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    }
    [Environment]::SetEnvironmentVariable('TRANSLATE_DROP_COUNT', [string]$resolvedFiles.Count, 'Process')
    for ($index = 0; $index -lt $resolvedFiles.Count; $index++) {
        [Environment]::SetEnvironmentVariable("TRANSLATE_DROP_$($index + 1)", $resolvedFiles[$index], 'Process')
    }
    & $python @runnerArgs
    $result = $LASTEXITCODE
} finally {
    foreach ($name in $savedEnv.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedEnv[$name], 'Process')
    }
}
exit $result

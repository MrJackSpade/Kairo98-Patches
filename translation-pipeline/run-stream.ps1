param(
    [Parameter(Mandatory=$true)][string]$InputFile,
    [ValidateSet('deepseek','qwen','gemma')][string]$Model = 'deepseek',
    [int]$ContextTokens = 0,
    [int]$GpuLayers = -1,
    [int]$MaxFieldTokens = 3000,
    [string]$Work,
    [string]$Output,
    [int]$Limit = 0
)
$ErrorActionPreference = 'Stop'
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
$runnerArgs = @(
    (Join-Path $projectDir 'translate_stream.py'), $InputFile,
    '--model', $modelPath, '--model-tag', $Model,
    '--context-tokens', [string]$ContextTokens,
    '--max-field-tokens', [string]$MaxFieldTokens
)
if ($GpuLayers -ge 0) { $runnerArgs += @('--gpu-layers', [string]$GpuLayers) }
if ($Work) { $runnerArgs += @('--work', $Work) }
if ($Output) { $runnerArgs += @('--output', $Output) }
if ($Limit -gt 0) { $runnerArgs += @('--limit', [string]$Limit) }
& $python @runnerArgs
exit $LASTEXITCODE

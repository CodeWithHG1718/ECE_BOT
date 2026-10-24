param([switch]$NoLLM, [switch]$Warmup)
$ErrorActionPreference = 'Stop'
$signalPython = Join-Path $PSScriptRoot '.venv-embeddings/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $signalPython)) {
    throw 'Set up the local Python environment first; see docs/telegram-implementation.md.'
}
Push-Location $PSScriptRoot
$signalPreviousLlm = $env:SIGNAL_LLM
$signalPreviousEndpoint = $env:SIGNAL_OLLAMA_URL
try {
    if ($NoLLM) { $env:SIGNAL_LLM = 'off' }
    elseif ($env:SIGNAL_LLM -notin @('off','0','false')) {
        $signalPortable = Join-Path $PSScriptRoot '.cache/ollama-v0.24.0/ollama.exe'
        $signalInstalled = Get-Command ollama -ErrorAction SilentlyContinue
        $signalExecutable = if (Test-Path -LiteralPath $signalPortable) { $signalPortable } elseif ($signalInstalled) { $signalInstalled.Source } else { $null }
        if ($signalExecutable) {
            $signalDefaultEndpoint = if ($signalExecutable -eq $signalPortable) { 'http://127.0.0.1:11435' } else { 'http://127.0.0.1:11434' }
            $signalEndpoint = if ($env:SIGNAL_OLLAMA_URL) { $env:SIGNAL_OLLAMA_URL } else { $signalDefaultEndpoint }
            $signalUri = [uri]$signalEndpoint
            if ($signalUri.Scheme -ne 'http' -or $signalUri.Host -notin @('localhost','127.0.0.1','[::1]')) {
                throw 'SIGNAL_OLLAMA_URL must be a local HTTP loopback address.'
            }
            $env:SIGNAL_OLLAMA_URL = $signalEndpoint
            try {
                $null = Invoke-RestMethod -Uri "$signalEndpoint/api/version" -TimeoutSec 2
            } catch {
                if ($signalEndpoint -eq $signalDefaultEndpoint) {
                    $signalLogs = Join-Path $PSScriptRoot 'tmp'
                    $null = New-Item -ItemType Directory -Path $signalLogs -Force
                    $signalSavedEnvironment = @{}
                    $signalServiceEnvironment = @{
                        OLLAMA_HOST=$signalEndpoint; OLLAMA_NO_CLOUD='1';
                        OLLAMA_CONTEXT_LENGTH='4096'; OLLAMA_NUM_PARALLEL='1';
                        OLLAMA_MAX_LOADED_MODELS='1'; OLLAMA_FLASH_ATTENTION='1'
                    }
                    try {
                        foreach ($signalName in $signalServiceEnvironment.Keys) {
                            $signalSavedEnvironment[$signalName] = [Environment]::GetEnvironmentVariable($signalName,'Process')
                            [Environment]::SetEnvironmentVariable($signalName,$signalServiceEnvironment[$signalName],'Process')
                        }
                        Start-Process -FilePath $signalExecutable -ArgumentList 'serve' -WindowStyle Hidden `
                            -RedirectStandardOutput (Join-Path $signalLogs 'ollama-serve.out.log') `
                            -RedirectStandardError (Join-Path $signalLogs 'ollama-serve.err.log')
                    } finally {
                        foreach ($signalName in $signalSavedEnvironment.Keys) {
                            [Environment]::SetEnvironmentVariable($signalName,$signalSavedEnvironment[$signalName],'Process')
                        }
                    }
                    for ($signalAttempt=0; $signalAttempt -lt 15; $signalAttempt++) {
                        Start-Sleep -Milliseconds 400
                        try {
                            $null = Invoke-RestMethod -Uri "$signalEndpoint/api/version" -TimeoutSec 1
                            break
                        } catch { }
                    }
                }
            }
        }
    }
    $signalArguments = @('-X','utf8','-m','bot.local_chat')
    if ($Warmup) { $signalArguments += '--warmup' }
    & $signalPython @signalArguments
} finally {
    $env:SIGNAL_LLM = $signalPreviousLlm
    $env:SIGNAL_OLLAMA_URL = $signalPreviousEndpoint
    Pop-Location
}

$ErrorActionPreference = 'Stop'
$taskDev = Split-Path $PSScriptRoot -Parent
$taskPrivate = Join-Path $taskDev 'private'
$env:JADX_CONFIG_DIR = Join-Path $taskPrivate 'jadx_config'
$env:JADX_CACHE_DIR = Join-Path $taskPrivate 'jadx_cache'
$env:JADX_TMP_DIR = Join-Path $taskPrivate 'jadx_tmp'
$taskInputs = @(Get-ChildItem -LiteralPath (Join-Path $taskPrivate 'analyzer_1_5_6_dex') -Filter '*.dex' | ForEach-Object FullName)
if ($taskInputs.Count -eq 0) { throw 'No DEX inputs' }
$taskOutput = Join-Path $taskPrivate 'analyzer_1_5_6_java'
if (Test-Path -LiteralPath $taskOutput) { throw 'Output already exists; preserve it and select a new run directory.' }
& (Join-Path $taskPrivate 'jadx-1.5.6/bin/jadx.bat') --config none -r -j 2 --no-inline-methods --no-inline-anonymous --log-level warn -d $taskOutput @taskInputs
exit $LASTEXITCODE

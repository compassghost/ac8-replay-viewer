# Builds dist\ac8-replay-viewer.zip: the viewer, tooling and ONE sample replay (Mission 1 = Mission ID 2 = Replay12).
# The working exports in this folder are not touched: the sample is re-derived from the save in a staging copy.
#   .\package.ps1 [-Sample Replay12] [-Saves <SaveGames folder>]
param(
  [string]$Sample = 'Replay12',
  [string]$Saves = "$env:LOCALAPPDATA\BANDAI NAMCO Entertainment\ACE COMBAT 8\Saved\SaveGames"
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$name = 'ac8-replay-viewer'
$stage = Join-Path $root "dist\$name"
$zip = Join-Path $root "dist\$name.zip"
$sav = Join-Path $Saves "$Sample.sav"
if (-not (Test-Path $sav)) { throw "Save not found: $sav" }
if (-not (Test-Path (Join-Path $root "$Sample.json"))) { throw "$Sample.json not found next to this script (export it first)." }

if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force $stage, "$stage\video-tools" | Out-Null

# Viewer source, converter tooling, docs. Deliberately NOT included: other replays, game-analysis scripts, evidence dumps, handoff notes, node_modules.
$files = 'viewer.template.html','playback.mjs','build_viewer.py','build_index.py','ac8_replay.py','attribute_kills.py','add_missiles.py','round_export.py','validate_replays.py','enums.json','FORMAT.md','README.md','RUNBOOK.md','demo.html'
foreach ($f in $files) { Copy-Item (Join-Path $root $f) $stage }
foreach ($f in 'render_video.mjs','package.json','package-lock.json') { Copy-Item (Join-Path $root "video-tools\$f") "$stage\video-tools" }

# Sample replay: regenerate attribution/projectiles from the save, then round, all on the staging copy.
Copy-Item (Join-Path $root "$Sample.json") $stage
Push-Location $stage
try {
  python attribute_kills.py $sav "$Sample.json"
  python add_missiles.py $sav "$Sample.json"
  python round_export.py "$Sample.json" --no-backup
  python build_index.py --default "$Sample.json"
  python build_viewer.py --out index.html
} finally { Pop-Location }

# Launch helpers (written separately so the line endings are right for each platform).
$ps1 = @(
  '# Serves this folder at http://localhost:5678/ (Python 3.10+ required)',
  '$py = Get-Command python -ErrorAction SilentlyContinue',
  'if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }',
  'if (-not $py) { throw ''Python was not found on PATH.'' }',
  'Write-Host ''Replay viewer: http://localhost:5678/  (Ctrl+C to stop)''',
  '& $py.Source -m http.server 5678 --bind 127.0.0.1 --directory $PSScriptRoot'
) -join "`r`n"
[IO.File]::WriteAllText((Join-Path $stage 'serve.ps1'), $ps1 + "`r`n", (New-Object Text.UTF8Encoding($true)))
$sh = @(
  '#!/bin/sh',
  '# Serves this folder at http://localhost:5678/ (Python 3.10+ required)',
  'cd "$(dirname "$0")" && echo "Replay viewer: http://localhost:5678/  (Ctrl+C to stop)" && python3 -m http.server 5678 --bind 127.0.0.1'
) -join "`n"
[IO.File]::WriteAllText((Join-Path $stage 'serve.sh'), $sh + "`n", (New-Object Text.UTF8Encoding($false)))

Get-ChildItem $stage -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $stage -DestinationPath $zip -CompressionLevel Optimal
Get-Item $zip | ForEach-Object { "{0}  {1:N1} MB" -f $_.FullName, ($_.Length / 1MB) }

# Builds dist\ac8-replay-viewer.zip: the viewer, tooling and two sample replays (Mission 2 = Replay13, default; Mission 4 = Replay7).
# The working exports in this folder are not touched: the samples are re-derived from the saves in a staging copy.
#   .\package.ps1 [-Sample Replay13,Replay7] [-Saves <SaveGames folder>]   (the first sample is the default)
param(
  [string[]]$Sample = @('Replay13', 'Replay7'),   # Mission 2 (default) and Mission 4
  [string]$Saves = "$env:LOCALAPPDATA\BANDAI NAMCO Entertainment\ACE COMBAT 8\Saved\SaveGames"
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$name = 'ac8-replay-viewer'
$stage = Join-Path $root "dist\$name"
$zip = Join-Path $root "dist\$name.zip"
foreach ($s in $Sample) {
  if (-not (Test-Path (Join-Path $Saves "$s.sav"))) { throw "Save not found: $(Join-Path $Saves "$s.sav")" }
  if (-not (Test-Path (Join-Path $root "$s.json"))) { throw "$s.json not found next to this script (export it first)." }
}

if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force $stage, "$stage\video-tools" | Out-Null

# Viewer source, converter tooling, docs. Deliberately NOT included: other replays, game-analysis scripts, evidence dumps, handoff notes, node_modules.
$files = 'viewer.template.html','playback.mjs','build_viewer.py','build_index.py','ac8_replay.py','attribute_kills.py','add_missiles.py','round_export.py','validate_replays.py','enums.json','FORMAT.md','README.md','RUNBOOK.md','demo.html'
foreach ($f in $files) { Copy-Item (Join-Path $root $f) $stage }
foreach ($f in 'render_video.mjs','package.json','package-lock.json') { Copy-Item (Join-Path $root "video-tools\$f") "$stage\video-tools" }

# Sample replay: regenerate attribution/projectiles from the save, then round, all on the staging copy.
foreach ($s in $Sample) { Copy-Item (Join-Path $root "$s.json") $stage; $ov = Join-Path $root "$s.overrides.json"; if (Test-Path $ov) { Copy-Item $ov $stage } }
Push-Location $stage
try {
  foreach ($s in $Sample) {
    $sav = Join-Path $Saves "$s.sav"
    python attribute_kills.py $sav "$s.json"
    python add_missiles.py $sav "$s.json"
    python round_export.py "$s.json" --no-backup
  }
  python build_index.py --default "$($Sample[0]).json"
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

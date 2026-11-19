# Runbook

## Requirements

| For | You need |
|---|---|
| Viewing | A browser (Edge or Chrome) and any static web server. `python -m http.server` is enough. |
| Converting saves | Python 3.10+ (standard library only). |
| Rendering video | Node.js 18+, Edge or Chrome installed, and `npm install` in `video-tools` (downloads puppeteer-core and ffmpeg-static). |

## 1. Run locally

```powershell
python -m http.server 5678
```

Open <http://localhost:5678/>. `serve.ps1` (Windows) and `serve.sh` (macOS/Linux) do the same thing and print the address.

## 2. Deploy as a static site

The viewer is plain static files. Copy the folder to any web host (IIS, nginx, S3/CloudFront, GitHub Pages, ...).

- Serve over **HTTP(S)**. The page fetches `replays.json` and the selected replay; `file://` will not work.
- Everything is same-origin, so no CORS settings are needed.
- Enable **gzip/brotli** for `.json`. Replay files are large (a 34-minute mission is about 35 MB uncompressed) and compress very well.
- After you change `replays.json` or a replay file, browsers may serve a cached copy. Hard-refresh (Ctrl+F5) or add cache headers
  that revalidate JSON.
- Only the files in the table in `README.md` are needed to run. The Python and Node files are optional tooling.

## 3. Add a replay

Replay saves are in `%LOCALAPPDATA%\BANDAI NAMCO Entertainment\ACE COMBAT 8\Saved\SaveGames\Replay<N>.sav`.
Work on copies of the output only; the tools never write to the save.

Mission ID is stored in each save's header. The mission number is Mission ID - 1.

For a save `Replay5.sav` (adjust the path):

```powershell
$sav = "$env:LOCALAPPDATA\BANDAI NAMCO Entertainment\ACE COMBAT 8\Saved\SaveGames\Replay5.sav"
python ac8_replay.py $sav --export .\Replay5.json     # 1. convert tracks and events
python attribute_kills.py $sav .\Replay5.json          # 2. infer who destroyed what (from projectile geometry)
python add_missiles.py $sav .\Replay5.json             # 3. add projectile tracks for the Projectiles button
python round_export.py .\Replay5.json --no-backup      # 4. shrink the file (cm / ms / 4-decimal quaternions)
python build_index.py --default Replay5.json           # 5. regenerate replays.json (the one marked --default loads first)
```

Keep the output named `Replay<N>.json`; `build_index.py` picks up every `Replay*.json` in the folder.
Steps 2-4 are optional; without them the replay still plays, with no kill credit, projectiles or size reduction.
Steps 2 and 3 re-derive their data each time, so they are safe to re-run. Step 4 rounds in place: run it once per export.

To validate a batch of saves: `python validate_replays.py <save folder>`.

### Adding names

Callsigns come from the save's recorded labels. To name an aircraft the save does not label, add a `displayName` to the unit in
the replay JSON (units are listed under `units`, identified by `id`):

```json
{ "id": 1435, "displayName": "Brand", "nameSource": "user assignment" }
```

Any aircraft with a `displayName` counts as "named" in Display Settings. Names are always shown in capitals.

## 4. Render a video (offline)

```powershell
cd video-tools
npm install
node render_video.mjs ..\Replay12.json --speed 20 --out ..\clip.mp4
```

No visible browser window opens, and rendering is deterministic (frame-by-frame, not real time).

The easiest way to get the right options is the viewer's **Capture** panel: frame the shot (and optionally draw a frame
rectangle and set start/end markers), then press **Copy command** and run it from the package folder. It captures the camera
mode, angle, zoom, Projectiles button and label choices.

Main options:

| Option | Meaning |
|---|---|
| `--from S --to S` | Time range in seconds (default: whole replay). |
| `--speed N` | Replay speed, 1 to 40 (default 20). |
| `--fps N` | Output frame rate (default 30). |
| `--view 3d\|top` | Projection. `--yaw` and `--elevation` set the 3D angle in degrees; `--zoom` sets zoom. |
| `--camera whole\|dynamic\|player\|selected\|target` | Camera mode. `selected` and `target` need `--unit <id>`; `target` also takes `--target <id>`. |
| `--frame x0,y0,x1,y1` | A framing rectangle in view-plane metres (from the Capture panel). |
| `--missiles` | Show projectiles. |
| `--components` | Show components (a ship's guns, missile cells, turrets) as small markers. |
| `--plates a,b,...` | Label groups: `player,wingmen,namedAllies,alliedUnits,namedEnemies,enemyUnits` (or `none`). |
| `--size WxH` | Output size, at most 800x800. Default is 800x450 (16:9); a drawn frame keeps its own ratio. |
| `--crf N` | Quality: lower is sharper and larger (default 18). |
| `--out file.mp4` | Output file. |
| `--browser path` | Path to `msedge.exe` / `chrome.exe` if it is not in a standard location. |

Frames are captured as lossless PNG and encoded with H.264 (`yuv420p`, `slow` preset). Expect a 34-minute mission at 10x to take
several minutes.

## 5. Change the viewer

Edit `viewer.template.html` (not `index.html`, which is generated), then rebuild:

```powershell
python build_viewer.py --out index.html
```

By default no replay is embedded. `python build_viewer.py --embed Replay12.json --out index.html` makes a self-contained copy that
also works from `file://` (the page grows by the size of the replay).

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| "No replay is embedded in this page..." | Serve over HTTP (step 1) or use **Open replay JSON**. |
| A newly added replay is missing from the selector | Re-run `build_index.py`, then hard-refresh (Ctrl+F5). |
| Page loads but the replay is slow | Enable gzip on the server; round the export (step 4 above). |
| `render_video.mjs`: "No Edge/Chrome found" | Pass `--browser "C:\path\to\msedge.exe"`. |
| `render_video.mjs`: cannot find module | Run `npm install` inside `video-tools`. |
| Wrong or missing killer for a kill | Expected for some kills: attribution is inferred. See the notes in `README.md`. |
| Save rejected | Only `SavedVersion` 32 is supported. |

## Notes on data

- Kill credit rule: a kill is credited to the projectile whose flight ends at the moment of destruction. Earlier hits that only
  damaged the target, and projectile objects that merely linger after impact, do not win. The player's own gun rounds are not
  recorded, so player gun kills are inferred from aim and are marked as such.
- Weapon label: a projectile that accelerates (by 15% or more over its flight) is a missile; a constant-speed one is a gun.
- Slow, sparsely sampled shells (artillery) are kept for their whole flight; a projectile is only cut where it actually stops.
- Units mounted on another unit (a ship's guns and missile cells, a tank's turret) are treated as parts of the parent: they get
  no label, kill marker or kill credit.
- See `FORMAT.md` for the binary and JSON layout.

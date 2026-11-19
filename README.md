# ACE COMBAT 8 tactical replay viewer

A browser viewer for the post-mission tactical replay in ACE COMBAT 8 (the radar-style view with moving aircraft markers).
It reads the replay save files the game already writes, converts them to JSON, and plays them back with a 3D wireframe view,
kill tracking, projectile display and an offline video renderer. It is read-only: it never touches the game, and the original
`.sav` files are never modified.

This package contains the viewer and two sample replays: **Mission 2** (Mission ID 3, 7:02, loads first) and **Mission 4** (Mission ID 5, 5:16). Pick between them in the replay selector.

## Quick start

You need Python 3.10 or newer (no extra packages). From this folder:

```powershell
python -m http.server 5678
```

Open <http://localhost:5678/> in Edge or Chrome. The sample replay loads by itself.

The page must be served over HTTP. Opening `index.html` directly from disk (`file://`) cannot fetch `replays.json`; use the
**Open replay JSON** button there to load a file by hand.

Mission numbers follow the game's mission numbering: **Mission number = Mission ID - 1** (Mission ID 3 is Mission 2).

## Using the viewer

- **Playback:** Play, -5 s / +5 s, the timeline, and a speed slider. Click a marker to select it.
- **View:** *3D view* (orthographic, drag to orbit, scroll to zoom), *Top down*, *Reset view*.
- **Camera dropdown:** Whole mission, Follow pilot, Dynamic (combat) (fits the combat-relevant area), Dynamic (target)
  (frames the selected aircraft and a locked target), Follow selected.
- **Top left:** *Unit Info* (details for the selected unit, with Lock), *Unit Tracker* (search units, see their kills and who
  destroyed them; clicking a kill jumps to 1 s before it and centres on the target), *Display Settings* (show projectiles, on by default and including the player's firing line; show components such as a ship's guns and missile cells, track component kills such as AA guns and turrets, and which units get name labels).
- **Capture:** draw a framing rectangle, set start/end markers and copy a command for the offline video renderer
  (see `RUNBOOK.md`).
- **Replay selector** (top right): switches between the replays listed in `replays.json`.

Colours (matching the in-game replay): green = player and wingmen, light blue = other allies, orange-red = enemies, yellow = unidentified, grey = scenery that is not a real target.
Aircraft are wireframe dorito shapes oriented by the recorded attitude; ground vehicles are cubes; ships with a recorded heading
are pentagonal prisms. Red lines run from an attacker to its target for 10 s after a kill.

## Privacy and safety

- **Everything runs locally.** The viewer is static files. It reads `replays.json` and the replay you pick from the same folder or
  site, and **Open replay JSON** reads a file in your browser without uploading it.
- **Enforced, not just promised.** The page carries a content security policy (`connect-src 'self'`), so the browser blocks any
  request to another site. You can check it in the page source.
- **Readable tooling.** The converters use only the Python standard library and never modify your `.sav` files. The optional video
  renderer installs puppeteer-core and ffmpeg-static through `npm install`.
- **Keep saves to yourself.** Convert them with the scripts here; don't send `.sav` files to third-party converters.
- A hosted copy of this page (for example GitHub Pages) is only a preview of the sample missions. For your own replays, run the
  package on your computer.

## Why kill credit is only inferred

The replay does not track kills. It stores positions, health, a destroyed flag, projectiles (missiles and AI gun rounds) and the player's trigger. Credit is a reconstruction, so treat every kill as a best guess:

- A destruction has no recorded cause: a hit, a collision, a crash or debris all look the same.
- The shooter is the unit nearest a projectile's first sample, so aircraft in tight formation can be confused.
- A projectile near the victim at death may only have passed by; gun rounds do not home or explode near a target.
- The player's own gun rounds are not recorded. Player gun kills are guessed from the trigger (where the save has it) and the nose direction.
- Several shooters can damage one target; the credited one need not have dealt the killing damage.
- Trigger data exists only in some missions (1, 2 and 4 were checked); elsewhere only aim is used.
- Components, collateral kills and collisions are credited by proximity and timing.
- Some recordings end before the mission does, so later kills are missing.
- Kills where the player's trigger was also down are marked "player also firing".

## What to keep in mind

- Kill credit is **inferred** from projectile geometry. The save has no kill-credit field. Many kills have no identifiable
  shooter, and some attributions are marked uncertain (dashed kill lines).
- Positions are in metres. There is no terrain or map boundary in the saves; the background is a reference grid.
- Callsigns are the game's recorded labels. Where a save has none, names can be added by hand (see `RUNBOOK.md`).
- This is a diagnostic reconstruction, not a pixel-identical copy of the game's replay.

## Files

| File | Purpose |
|---|---|
| `index.html` | The viewer (no replay embedded; loads `replays.json` over HTTP). |
| `demo.html` | Landing page: embedded live demo and the self-service steps for using your own replays. |
| `replays.json` | List of replays the selector offers. |
| `Replay13.json`, `Replay7.json` | The samples: Mission 2 (Mission ID 3) and Mission 4 (Mission ID 5). |
| `RUNBOOK.md` | Deploying, adding replays, rendering video, troubleshooting. |
| `FORMAT.md` | Save and JSON format notes. |
| `ac8_replay.py` and the other `.py` files | Convert saves to JSON, attribute kills, add projectiles, round, rebuild the viewer. |
| `viewer.template.html`, `playback.mjs` | Viewer source; `build_viewer.py` combines them into `index.html`. |
| `video-tools/` | Offline (headless) video renderer. |

No game files, executables, archives or encryption keys are included. The sample JSON files contain only extracted replay telemetry.

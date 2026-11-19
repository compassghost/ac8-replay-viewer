# ACE COMBAT 8 tactical replay viewer

A browser viewer for the post-mission tactical replay in ACE COMBAT 8 (the radar-style view with moving aircraft markers).
It reads the replay save files the game already writes, converts them to JSON, and plays them back with a 3D wireframe view,
kill tracking, projectile display and an offline video renderer. It is read-only: it never touches the game, and the original
`.sav` files are never modified.

This package contains the viewer and one sample replay, **Mission 1** (Mission ID 2, 4:33).

## Quick start

You need Python 3.10 or newer (no extra packages). From this folder:

```powershell
python -m http.server 5678
```

Open <http://localhost:5678/> in Edge or Chrome. The sample replay loads by itself.

The page must be served over HTTP. Opening `index.html` directly from disk (`file://`) cannot fetch `replays.json`; use the
**Open replay JSON** button there to load a file by hand.

Mission numbers follow the game's mission numbering: **Mission number = Mission ID - 1** (Mission ID 2 is Mission 1).

## Using the viewer

- **Playback:** Play, -5 s / +5 s, the timeline, and a speed slider. Click a marker to select it.
- **View:** *3D view* (orthographic, drag to orbit, scroll to zoom), *Top down*, *Reset view*.
- **Camera dropdown:** Whole mission, Follow pilot, Dynamic (combat) (fits the combat-relevant area), Dynamic (target)
  (frames the selected aircraft and a locked target), Follow selected.
- **Top left:** *Unit Info* (details for the selected unit, with Lock), *Unit Tracker* (search units, see their kills and who
  destroyed them; clicking a kill jumps to 1 s before it and centres on the target), *Display Settings* (show projectiles, show components such as a ship's guns and missile cells, and which units get name labels).
- **Capture:** draw a framing rectangle, set start/end markers and copy a command for the offline video renderer
  (see `RUNBOOK.md`).
- **Replay selector** (top right): switches between the replays listed in `replays.json`.

Colours: blue = player/allies, red = enemies, yellow = unidentified, grey = scenery that is not a real target.
Aircraft are wireframe dorito shapes oriented by the recorded attitude; ground vehicles are cubes; ships with a recorded heading
are pentagonal prisms. Red lines run from an attacker to its target for 10 s after a kill.

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
| `Replay12.json` | The sample: Mission 1 (Mission ID 2). |
| `RUNBOOK.md` | Deploying, adding replays, rendering video, troubleshooting. |
| `FORMAT.md` | Save and JSON format notes. |
| `ac8_replay.py` and the other `.py` files | Convert saves to JSON, attribute kills, add projectiles, round, rebuild the viewer. |
| `viewer.template.html`, `playback.mjs` | Viewer source; `build_viewer.py` combines them into `index.html`. |
| `video-tools/` | Offline (headless) video renderer. |

No game files, executables, archives or encryption keys are included. The sample JSON contains only extracted replay telemetry.

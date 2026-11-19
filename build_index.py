"""Write replays.json: the list of extracted replay exports the viewer's selector offers.

Mission number = MissionID - 1 (MissionID 29 is mission M28). Preserve MapPath separately; it is shown as recorded.
Usage: python build_index.py [--default Replay3.json]
"""
import argparse, json, pathlib, re

root = pathlib.Path(__file__).parent
ap = argparse.ArgumentParser()
ap.add_argument('--default', default='Replay3.json', help='export embedded in reference-viewer.html and selected at startup')
args = ap.parse_args()

entries = []
for path in sorted(root.glob('Replay*.json'), key=lambda p: int(re.sub(r'\D', '', p.stem) or 0)):
    if path.name.endswith('-inspection.json'):
        continue
    doc = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(doc, dict) or doc.get('schema') != 'ac8-tactical-replay':
        continue
    mission = doc['mission']
    entries.append({
        'file': path.name,
        'missionId': mission['MissionID'],
        'missionNumber': mission['MissionID'] - 1,
        'mapPath': mission.get('MapPath'),
        'duration': doc['duration'],
        'markers': len(doc['units']),
        'killAttribution': any(e.get('attacker') for e in doc['events']),
        'default': path.name == args.default,
    })
entries.sort(key=lambda e: (not e['default'], e['missionId'], e['file']))
(root / 'replays.json').write_text(json.dumps(entries, indent=1), encoding='utf-8')
for e in entries:
    print(('* ' if e['default'] else '  ') + f"M{e['missionNumber']} (Mission ID {e['missionId']}) {e['file']} {e['duration']:.0f}s kills={e['killAttribution']}")

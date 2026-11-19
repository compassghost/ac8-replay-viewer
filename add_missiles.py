"""Add missile tracks to an exported replay JSON (read-only on the .sav).

Projectiles are unlabeled flag==2 objects with a translation track. Guns fly ~1.5 s, missiles longer, so anything that flies for MIN_SECONDS or longer is a missile.
Only the moving part of each track is kept: a projectile that has actually stopped (impact/expiry) is cut off there, so it
vanishes instead of lingering. Slow, sparsely sampled shells (artillery) are still moving, so they are kept for their whole flight. The shooter is inferred as the unit nearest the
first sample (within MAX_LAUNCH metres) - the same inference attribute_kills.py uses, not a native field.

Usage: python add_missiles.py Replay3.sav Replay3.json
Adds doc['missiles'] = [{id, shooterId, t0, t1, track: [[t, x, y, z], ...]}] (metres, thinned to >= SAMPLE_GAP s).
"""
import json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import ac8_replay as ac8
from attribute_kills import projectiles, unit_position, in_flight, weapon_of, VEHICLE_TYPES, MAX_LAUNCH

MIN_SECONDS = 2.0
SAMPLE_GAP = 0.25


def missiles(doc, projs):
    units = [u for u in doc['units'] if u['tracks']['position'] and u['iconType'] in VEHICLE_TYPES]
    for u in units:
        u['_times'] = [r[0] for r in u['tracks']['position']]
    result = []
    for pid, rows in projs:
        rows = in_flight(rows)
        # keep anything accelerating (a missile, even a short close-range one) and anything that flies for MIN_SECONDS or longer
        # (slow-moving or long-range shells, i.e. artillery)
        if len(rows) < 2 or (rows[-1][0] - rows[0][0] < MIN_SECONDS and weapon_of(rows) != 'missile'):
            continue
        shooter = None
        for u in units:
            if u['startTime'] > rows[0][0]:
                continue
            p = unit_position(u, rows[0][0])
            if not p or p == [0, 0, 0]:
                continue
            d = sum((a - b) ** 2 for a, b in zip(p, rows[0][1:])) ** 0.5
            if shooter is None or d < shooter[0]:
                shooter = (d, u['id'])
        track, last = [], None
        for i, r in enumerate(rows):
            if last is None or r[0] - last >= SAMPLE_GAP or i == len(rows) - 1:
                track.append([round(r[0], 2), round(r[1], 1), round(r[2], 1), round(r[3], 1)])
                last = r[0]
        result.append({'id': pid, 'shooterId': shooter[1] if shooter and shooter[0] <= MAX_LAUNCH else None,
                       't0': track[0][0], 't1': track[-1][0], 'track': track})
    for u in units:
        u.pop('_times', None)
    return sorted(result, key=lambda m: m['t0'])


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    sav, js = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    doc = json.loads(js.read_text(encoding='utf-8'))
    doc['missiles'] = missiles(doc, projectiles(ac8.Replay(sav)))
    note = 'missiles[] are projectile objects alive >= 2 s; shooterId is inferred from launch position'
    if note not in doc.setdefault('warnings', []):
        doc['warnings'].append(note)
    js.write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8', newline='')
    attributed = sum(1 for m in doc['missiles'] if m['shooterId'] is not None)
    print(f'{js.name}: {len(doc["missiles"])} missiles ({attributed} with inferred shooter)')


if __name__ == '__main__':
    main()

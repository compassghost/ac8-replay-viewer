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
from attribute_kills import projectiles, projectile_position, unit_position, in_flight, weapon_of, VEHICLE_TYPES, MAX_LAUNCH

MIN_SECONDS = 2.0
SAMPLE_GAP = 0.25
DROP_GAP = 3.0           # seconds between bombs of one drop


CHILD_METERS = 60.0     # a projectile that starts this close to another projectile in flight is its child (a submunition)
CHILD_GRACE = 0.3       # ...if the parent was still in flight, or ended no more than this long before
MIN_CHILDREN = 2        # a projectile that releases at least this many children is a bomb (dispenser), not a missile
UNIT_SNAP = 0.05        # shooters are looked up on a 50 ms grid, which gun bursts share


def missiles(doc, projs):
    """Returns (missiles, fire). missiles = projectile tracks for drawing (unchanged format). fire = per-unit launch times by kind."""
    units = [u for u in doc['units'] if u['tracks']['position'] and u['iconType'] in VEHICLE_TYPES]
    for u in units:
        u['_times'] = [r[0] for r in u['tracks']['position']]
    snaps = {}

    def positions(t):
        key = round(t / UNIT_SNAP)
        if key not in snaps:
            tt = key * UNIT_SNAP
            snaps[key] = [(u['id'], unit_position(u, tt)) for u in units if u['startTime'] <= tt]
        return snaps[key]

    def shooter_of(t, p):
        best = None
        for uid, q in positions(t):
            if not q or q == [0, 0, 0]:
                continue
            d = sum((a - b) ** 2 for a, b in zip(q, p)) ** 0.5
            if best is None or d < best[0]:
                best = (d, uid)
        return best if best and best[0] <= MAX_LAUNCH else None

    flights = []
    for pid, rows in projs:
        f = in_flight(rows)
        if len(f) < 2:
            continue
        flights.append({'id': pid, 'f': f, 't0': f[0][0], 't1': f[-1][0], 'kind': weapon_of(f), 'shooter': None})
    for x in flights:
        s = shooter_of(x['t0'], x['f'][0][1:])
        x['shooter'] = s[1] if s else None

    # Children: projectiles that start away from every unit, right on another projectile's path (SOD and similar bombs).
    launched = [x for x in flights if x['shooter'] is not None]
    children = {}
    for o in flights:
        if o['shooter'] is not None:
            continue
        best = None
        for q in launched:
            if q['t0'] > o['t0'] + 0.05 or q['t1'] < o['t0'] - CHILD_GRACE:
                continue
            pos = projectile_position(q['f'], min(max(o['t0'], q['t0']), q['t1']))
            if not pos:
                continue
            d = sum((a - b) ** 2 for a, b in zip(pos, o['f'][0][1:])) ** 0.5
            if d < CHILD_METERS and (best is None or d < best[0]):
                best = (d, q['id'])
        if best:
            children.setdefault(best[1], []).append(o['t0'])

    fire = {}
    drops = {}
    for x in launched:
        e = fire.setdefault(str(x['shooter']), {'m': [], 'b': []})
        kids = children.get(x['id'], [])
        if len(kids) >= MIN_CHILDREN:
            e['b'].append([round(x['t0'], 1), len(kids)])
        elif x['kind'] == 'bomb':   # lone dropped bombs are grouped into drops below
            drops.setdefault(str(x['shooter']), []).append(x['t0'])
        elif x['kind'] != 'gun':   # gun rounds are deliberately not counted: too many, and the player's are often not recorded

            e['m'].append(round(x['t0'], 1))
    for sid, times in drops.items():   # bombs released within DROP_GAP of each other are one drop (an SFFS circle or line is one drop of N bombs; an XSDB is a drop of 1)
        e = fire.setdefault(sid, {'m': [], 'b': []})
        times.sort(); start = prev = times[0]; n = 0
        for tt in times:
            if tt - prev > DROP_GAP:
                e['b'].append([round(start, 1), n]); start, n = tt, 0
            prev = tt; n += 1
        e['b'].append([round(start, 1), n])
    for e in fire.values():
        e['m'].sort(); e['b'].sort()

    result = []
    for x in flights:
        rows = x['f']
        # keep anything accelerating (a missile, even a short close-range one) and anything that flies for MIN_SECONDS or longer
        # (slow-moving or long-range shells, i.e. artillery)
        if rows[-1][0] - rows[0][0] < MIN_SECONDS and x['kind'] not in ('missile', 'bomb'):
            continue
        track, last = [], None
        for i, r in enumerate(rows):
            if last is None or r[0] - last >= SAMPLE_GAP or i == len(rows) - 1:
                track.append([round(r[0], 2), round(r[1], 1), round(r[2], 1), round(r[3], 1)])
                last = r[0]
        result.append({'id': x['id'], 'shooterId': x['shooter'], 't0': track[0][0], 't1': track[-1][0], 'track': track})
    for u in units:
        u.pop('_times', None)
    return sorted(result, key=lambda m: m['t0']), fire

def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    sav, js = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    doc = json.loads(js.read_text(encoding='utf-8'))
    doc['missiles'], doc['fire'] = missiles(doc, projectiles(ac8.Replay(sav)))
    for note in ('missiles[] are projectile objects alive >= 2 s; shooterId is inferred from launch position',
                 'fire{} counts missiles (m) and bombs (b: [time, children]) launched per unit, inferred from launch position; gun rounds are not counted'):
        if note not in doc.setdefault('warnings', []):
            doc['warnings'].append(note)
    js.write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8', newline='')
    attributed = sum(1 for m in doc['missiles'] if m['shooterId'] is not None)
    bombs = sum(len(e['b']) for e in doc['fire'].values()); kids = sum(c for e in doc['fire'].values() for _, c in e['b'])
    print(f'{js.name}: {len(doc["missiles"])} missiles ({attributed} with inferred shooter); fire: {sum(len(e["m"]) for e in doc["fire"].values())} missiles, {bombs} bombs ({kids} submunitions)')


if __name__ == '__main__':
    main()

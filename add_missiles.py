"""Add missile tracks to an exported replay JSON (read-only on the .sav).

Projectiles are unlabeled flag==2 objects with a translation track. Guns fly ~1.5 s, missiles longer, so anything that flies for MIN_SECONDS or longer is a missile.
Only the moving part of each track is kept: a projectile that has actually stopped (impact/expiry) is cut off there, so it
vanishes instead of lingering. Slow, sparsely sampled shells (artillery) are still moving, so they are kept for their whole flight. The shooter is inferred as the unit nearest the
first sample (within MAX_LAUNCH metres) - the same inference attribute_kills.py uses, not a native field.

Usage: python add_missiles.py Replay3.sav Replay3.json
Adds doc['missiles'] = [{id, shooterId, t0, t1, track: [[t, x, y, z], ...]}] (metres, thinned to >= SAMPLE_GAP s).
"""
import json, pathlib, re, sys

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

# Special-weapon IDs in the header's PlayerPlaneInfos (PlaneSWP1/2), named from user-supplied loadouts. Some are probable, not certain.
SPW_NAMES = {16: 'LAAM', 21: 'QAAM', 24: 'SASM', 27: 'SOD', 41: 'IEWS', 4: '4AAM', 33: 'MPBM', 28: 'TLS', 17: 'LACM', 20: 'MGP', 18: 'LAGM', 19: 'LASM', 13: 'HCAA', 31: 'XSDB', 26: 'SFFS'}
STANDARD_WEAPON = 'MSL'
CYCLE_PAIR = {'001df547': 'D', '0013f547': '3'}   # type 69 value that comes with each type 71 weapon-cycle press


def saved_loadout_names(replay):
    """Weapon1/Weapon2 names from the save's own retry data (e.g. ['LAAM', 'QAAM']), or [] if absent."""
    buf = bytes(replay.buffer)
    i = buf.find(b'LiveReplayBeginingStatus')
    if i < 0:
        return []
    return [m.group(1).decode().upper() for m in re.finditer(rb'ELiveWeaponID::WID_(\w+)', buf[i:i + 600])][:2]


def label_player_weapons(doc, header, missiles_, saved_weapon_names=None):
    """Name the weapon of each player launch. The player cycles forward standard -> SPW1 -> SPW2 -> standard with each type 71 press
    (a type 69 value 001df547 lands on SPW1, 0013f547 on the others); the slot at launch time gives the header's SPW ID. Skipped
    when the observed press sequence does not follow that cycle (a weapon ran out, or backwards presses)."""
    player = next((u for u in doc['units'] if u.get('isPlayer')), None)
    infos = header.get('PlayerPlaneInfos') if isinstance(header, dict) else None
    if not player or not isinstance(infos, list) or not infos or not isinstance(infos[0], dict):
        return None
    spw = [infos[0].get(k) for k in ('PlaneSWP1', 'PlaneSWP2')]
    spw = [i for i in spw if isinstance(i, int) and i > 0]
    # The save names the player's loadout itself (ReplayRetryData.BeginingStatus Weapon1/Weapon2 = ELiveWeaponID::WID_<name>); use that
    # when it agrees in count with the header, else fall back to the ID table.
    named = saved_weapon_names or []
    names = named if len(named) == len(spw) else [SPW_NAMES.get(i, f'SPW{n + 1} (ID {i})') for n, i in enumerate(spw)]
    slots = [STANDARD_WEAPON] + names
    events = sorted((e for e in doc.get('rawUnitEvents', []) if e['unitId'] == player['id']), key=lambda e: e['t'])
    presses = []
    for e in events:
        if e['recordType'] == 71 and e['payloadHex'] == '04000000':
            pair = next((x for x in events if x['recordType'] == 69 and abs(x['t'] - e['t']) <= 0.05 and x['payloadHex'] in CYCLE_PAIR), None)
            presses.append((e['t'], CYCLE_PAIR[pair['payloadHex']] if pair else '?'))
    n = len(slots)
    regular = all(v == ('D' if i % n == 0 else '3') for i, (_, v) in enumerate(presses))
    info = {'planeId': infos[0].get('PlaneID'), 'spwIds': spw, 'slots': slots, 'presses': len(presses), 'cycleRegular': regular}
    if n == 2 and all(v in 'D3' for _, v in presses):
        # One special weapon: only two states, so the last press names the slot directly (D = the SPW, 3 = standard), even when a
        # press was missed or repeated and the strict cycle breaks.
        times = [t for t, _ in presses]
        for m in missiles_:
            if m['shooterId'] == player['id']:
                last = [v for t, v in presses if t <= m['t0']]
                m['weapon'] = slots[1] if last and last[-1] == 'D' else slots[0]
        info['cycleRegular'] = regular
        return info
    if not regular:
        return info
    times = [t for t, _ in presses]
    for m in missiles_:
        if m['shooterId'] == player['id']:
            m['weapon'] = slots[sum(1 for t in times if t <= m['t0']) % n]
    return info


AIR_MISSILES = {'LAAM', 'QAAM', 'SAAM', '2AAM', '4AAM', '6AAM', 'HCAA', 'HPAA'}                 # can hit aircraft
GROUND_MISSILES = {'LACM', 'LAGM', 'LASM', 'SASM', '4AGM', '6AGM', '8AGM'}                      # ground/ship targets only
MSL_LOCK_METERS = 2000.0     # the standard MSL only locks within this range (user-supplied; it can target both air and ground)
WINGMAN_END_METERS = 150.0
# A wingman's preset weapon pair per plane ID, as stored in the header slots, and the plane ID for an aircraft label seen in a spawn group.
PLANE_WINGMAN_SPW = {14010: (17, 16), 18010: (24, 27), 19010: (41, 4), 38010: (33, 28)}
LABEL_PLANES = {'RAFALE M': 14010}
LATE_SPAWN_SECONDS = 1.0     # a wingman that appears after the start is brought in by the mission, not taken from the player's slots
GROUP_SPAWN_WINDOW = 0.5     # same spawn time as the group (seconds)
GROUP_ID_SPAN = 60           # and object ids close to hers


def late_group_plane(doc, wingman):
    """Plane ID for a wingman who joins late together with a group of units that all carry one aircraft label (Little Bee arrives in M28
    with eight RAFALE M, consecutive object ids, same spawn time, and the same unknown-then-allied state change), else None."""
    if wingman['startTime'] <= LATE_SPAWN_SECONDS:
        return None
    labels = {str(u.get('recordedLabel') or '').upper() for u in doc['units']
              if not u.get('isWingman') and not u.get('isPlayer') and abs(u['startTime'] - wingman['startTime']) <= GROUP_SPAWN_WINDOW
              and abs(u['id'] - wingman['id']) <= GROUP_ID_SPAN}
    return LABEL_PLANES.get(next(iter(labels))) if len(labels) == 1 else None


def label_wingman_weapons(doc, header, missiles_):
    """Wingmen carry a preset loadout fixed by their airframe: the standard MSL plus the two weapons stored in their header slot
    (PlaneSWP1/2). A launch is named only when the weapon rules leave a single candidate: beyond MSL_LOCK_METERS it cannot be the MSL,
    an air-to-air missile needs an air target and a ground missile a ground or ship target. The target is the unit nearest the
    projectile's last sample (within WINGMAN_END_METERS). Otherwise the launch stays unnamed."""
    infos = header.get('PlayerPlaneInfos') if isinstance(header, dict) else None
    if not isinstance(infos, list) or len(infos) < 4:
        return []
    units = [u for u in doc['units'] if u['tracks']['position']]
    for u in units:
        u['_times'] = [r[0] for r in u['tracks']['position']]
    loadouts, allowed = [], {}
    # Callsigns change between missions (Professor, Little Bee, two wingmen only...), so no slot is tied to a name: the wingmen present
    # (one unit per callsign, in object-id order) take the filled header slots in order, and the mission is skipped when the counts differ.
    wingmen, seen = [], set()
    for u in sorted((x for x in doc['units'] if x.get('isWingman')), key=lambda x: x['id']):
        label = str(u.get('recordedLabel') or u.get('displayName') or '').upper()
        if label not in seen:
            seen.add(label)
            wingmen.append((u, label))
    filled = [i for i in infos[1:4] if isinstance(i, dict) and isinstance(i.get('PlaneID'), int) and i['PlaneID'] > 0]
    # A wingman the mission brings in late is not in the player's slots; she flies the aircraft of the group she spawns with.
    fixed = {label: plane for u, label in wingmen if (plane := late_group_plane(doc, u))}
    assigned = [(u, label, {'PlaneID': fixed[label], 'PlaneSWP1': PLANE_WINGMAN_SPW[fixed[label]][0], 'PlaneSWP2': PLANE_WINGMAN_SPW[fixed[label]][1]})
                for u, label in wingmen if label in fixed]
    wingmen = [(u, label) for u, label in wingmen if label not in fixed]
    if len(wingmen) != len(filled):
        return []
    assigned += [(u, label, info) for (u, label), info in zip(wingmen, filled)]
    for u, label, info in assigned:
        spw = [SPW_NAMES.get(i, f'ID {i}') for i in (info.get('PlaneSWP1'), info.get('PlaneSWP2')) if isinstance(i, int) and i > 0]
        for twin in doc['units']:   # a callsign can have more than one unit (a respawned wingman): same loadout
            if twin.get('isWingman') and str(twin.get('recordedLabel') or twin.get('displayName') or '').upper() == label:
                allowed[twin['id']] = [STANDARD_WEAPON] + spw
        loadouts.append({'unitId': u['id'], 'callsign': label, 'planeId': info['PlaneID'], 'weapons': [STANDARD_WEAPON] + spw})
    for m in missiles_:
        options = allowed.get(m['shooterId'])
        if not options or 'weapon' in m or len(m['track']) < 2:
            continue
        end = m['track'][-1]
        best = None
        for u in units:
            if u['id'] == m['shooterId'] or u['startTime'] > end[0]:
                continue
            p = unit_position(u, end[0])
            if p and p != [0, 0, 0]:
                d = sum((a - b) ** 2 for a, b in zip(p, end[1:])) ** 0.5
                if best is None or d < best[0]:
                    best = (d, u)
        shooter = next((u for u in units if u['id'] == m['shooterId']), None)
        if not best or best[0] > WINGMAN_END_METERS or not shooter:
            continue
        target = best[1]
        sp, tp = unit_position(shooter, m['t0']), unit_position(target, m['t0'])
        if not sp or not tp:
            continue
        air = target['iconType'] in ('Air', 'AirParent')
        far = sum((a - b) ** 2 for a, b in zip(sp, tp)) ** 0.5 > MSL_LOCK_METERS
        candidates = [w for w in options
                      if (w == STANDARD_WEAPON and not far)
                      or (w in AIR_MISSILES and air and far) or (w in GROUND_MISSILES and not air and far)]
        if len(candidates) == 1:
            m['weapon'] = candidates[0]
    for u in units:
        u.pop('_times', None)
    return loadouts


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    sav, js = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    doc = json.loads(js.read_text(encoding='utf-8'))
    replay = ac8.Replay(sav)
    doc['missiles'], doc['fire'] = missiles(doc, projectiles(replay))
    doc.pop('playerLoadout', None)
    loadout = label_player_weapons(doc, replay.outer.get('ReplayFileHeader'), doc['missiles'], saved_loadout_names(replay))
    if loadout:
        doc['playerLoadout'] = loadout
        note = 'missiles[].weapon names the weapon of a player launch, inferred from the weapon-cycle presses (record types 71/69) and the header SPW IDs'
        if note not in doc.setdefault('warnings', []):
            doc['warnings'].append(note)
    doc.pop('wingmanLoadouts', None)
    wingmen = label_wingman_weapons(doc, replay.outer.get('ReplayFileHeader'), doc['missiles'])
    if wingmen:
        doc['wingmanLoadouts'] = wingmen
        note = 'wingmanLoadouts[] list each wingman\'s preset weapons from its airframe; missiles[].weapon is set for a wingman launch only when range and target type leave a single candidate'
        if note not in doc.setdefault('warnings', []):
            doc['warnings'].append(note)
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

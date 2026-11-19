"""Infer who destroyed whom from projectile tracks (derived, not a native kill-credit field).

Findings this relies on (see FORMAT.md): the replay contains thousands of unlabeled, flag==2 objects whose
translation tracks are projectiles (guns ~1.5 s lifetime, missiles ~20-30 s). A projectile's first sample lies a few
metres from its shooter at launch time; a destroyed unit usually has a projectile within tens of metres at death time.

Usage: python attribute_kills.py Replay3.sav Replay3.json
Adds events[].attacker = {unitId, weapon, projectileId, missDistance, launchDistance, confidence} to destroyed events.
"""
import bisect, json, math, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import ac8_replay as ac8

VEHICLE_TYPES = ('Air', 'Naval', 'Ground', 'BuildingParent')
MAX_MISS = 200.0      # metres, projectile to victim at destruction time
MAX_LAUNCH = 60.0     # metres, shooter to projectile first sample
COLLATERAL_SECONDS = 6.0  # weak match this soon after a nearby kill is probably collateral
COLLATERAL_METERS = 450.0
PLAYER_GUN_METERS = 1500.0
PLAYER_GUN_DEGREES = 10.0
MAX_IMPACT_GAP = 2.0   # projectile objects linger after impact; a hit this long before death may not be the killing blow


STOPPED_SPEED = 20.0   # m/s; a projectile slower than this between two samples has stopped (it only lingers as an object)


def in_flight(rows):
    """The part of a projectile track where it is actually moving. Leading stationary samples are skipped and the track is cut at
    the first stationary segment (the object lingers after impact/expiry). A long gap between samples is NOT a stop: artillery and
    other slow shells are sampled sparsely but keep moving, so they stay."""
    def speed(a, b):
        dt = b[0] - a[0]
        return sum((p - q) ** 2 for p, q in zip(a[1:], b[1:])) ** 0.5 / dt if dt > 0 else None
    start = 0
    while start < len(rows) - 1 and (speed(rows[start], rows[start + 1]) or 0) < STOPPED_SPEED:
        start += 1
    end = len(rows)
    for i in range(start + 1, len(rows)):
        s = speed(rows[i - 1], rows[i])
        if s is not None and s < STOPPED_SPEED:
            end = i
            break
    return rows[start:end]


ACCEL_MISSILE = 0.15   # a missile's speed grows by at least this fraction over its flight; gun/cannon rounds hold a constant speed


def weapon_of(f):
    """'missile' if the in-flight projectile accelerates (rocket motor), else 'gun'. Flight time is a poor test: a missile
    fired at close range can hit in under 2 s. Falls back to flight time only when there are too few samples to measure speed."""
    sp = [sum((p - q) ** 2 for p, q in zip(a[1:], b[1:])) ** 0.5 / (b[0] - a[0]) for a, b in zip(f, f[1:]) if b[0] > a[0]]
    if len(sp) >= 3:
        n = max(1, len(sp) // 3)
        first, last = sum(sp[:n]) / n, sum(sp[-n:]) / n
        return 'missile' if (last - first) / max(first, 1.0) >= ACCEL_MISSILE else 'gun'
    return 'gun' if f[-1][0] - f[0][0] < 2 else 'missile'


def projectiles(replay):
    result = []
    for obj in replay.objects():
        if obj['flags'] != 2 or obj['channels'][1] < 0:
            continue
        rows = [(replay.unpack('<f', rec, 12)[0], *(v / 100 for v in replay.unpack('<3d', rec, rec['payload'])))
                for rec in replay.track(obj['channels'][1])]
        if rows:
            result.append((obj['id'], rows))
    return result


def unit_position(unit, t):
    rows = unit['tracks']['position']
    times = unit['_times']
    i = bisect.bisect_right(times, t) - 1
    if i < 0:
        return None
    a = rows[i]
    if i + 1 < len(rows) and rows[i + 1][0] > a[0] and not rows[i + 1][4]:
        b = rows[i + 1]
        f = (t - a[0]) / (b[0] - a[0])
        return [a[k] + (b[k] - a[k]) * f for k in (1, 2, 3)]
    return a[1:4]


def projectile_position(rows, t):
    times = [r[0] for r in rows]
    i = bisect.bisect_right(times, t) - 1
    if i < 0 or i >= len(rows) - 1:
        return None
    a, b = rows[i], rows[i + 1]
    f = (t - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0
    return [a[k] + (b[k] - a[k]) * f for k in (1, 2, 3)]


def attribute(doc, projs):
    units = [u for u in doc['units'] if u['tracks']['position'] and u['iconType'] in VEHICLE_TYPES]
    by_id = {u['id']: u for u in units}
    for u in units:
        u['_times'] = [r[0] for r in u['tracks']['position']]
    for event in doc['events']:
        event.pop('attacker', None)   # re-derive everything; stale attributions from an older rule must not survive
    flights = [(pid, rows, in_flight(rows)) for pid, rows in projs]
    flights = [x for x in flights if len(x[2]) >= 2]
    found = 0
    for event in doc['events']:
        if event.get('type') != 'destroyed' or event['unitId'] not in by_id:
            continue
        victim = by_id[event['unitId']]
        t = event['t']
        if not unit_position(victim, t):
            continue
        # The killing projectile is the one whose flight ENDS at the moment of destruction. Earlier hits that merely
        # damaged the target, and projectiles that only linger after impact, end too early and are skipped.
        best = None
        for pid, rows, f in flights:
            if f[0][0] > t or f[-1][0] < t - MAX_IMPACT_GAP:
                continue
            te = min(t, f[-1][0])
            q = projectile_position(f, te) if te < f[-1][0] else f[-1][1:]
            vp = unit_position(victim, te)
            if not q or not vp:
                continue
            d = math.dist(q, vp)
            if d >= MAX_MISS:
                continue
            gap = t - f[-1][0]
            key = (0, d) if abs(gap) <= 1.0 else (1, abs(gap))
            if best is None or key < best[0]:
                best = (key, d, pid, rows, f, gap)
        if not best:
            continue
        _, miss, pid, rows, f, gap = best
        shooter = None
        for u in units:
            if u['startTime'] > rows[0][0] or u['id'] == victim['id']:
                continue
            p = unit_position(u, rows[0][0])
            if not p or p == [0, 0, 0]:
                continue
            d = math.dist(p, rows[0][1:])
            if shooter is None or d < shooter[0]:
                shooter = (d, u)
        if not shooter or shooter[0] > MAX_LAUNCH:
            continue
        event['attacker'] = {
            'unitId': shooter[1]['id'],
            'weapon': weapon_of(f),
            'projectileId': pid,
            'missDistance': round(miss, 1),
            'launchDistance': round(shooter[0], 1),
            'impactTime': round(f[-1][0], 2),
            'secondsImpactToDeath': round(gap, 1),
            'confidence': 'inferred-high' if (miss < 50 and abs(gap) <= MAX_IMPACT_GAP) or (miss < 100 and abs(gap) <= 0.5) else 'inferred-low',
        }
        found += 1
    mark_collateral(doc, by_id)
    mark_player_guns(doc, units, by_id)
    for u in units:
        u.pop('_times', None)
    return found


def mark_collateral(doc, by_id):
    """A weak projectile match shortly after, and near, another attributed kill is probably debris/collision
    with that earlier kill. Re-label it 'collateral' and credit the earlier kill's shooter (still an inference)."""
    kills = [e for e in doc['events'] if e.get('type') == 'destroyed' and e['unitId'] in by_id]
    for event in kills:
        att = event.get('attacker')
        if not att or att['confidence'] != 'inferred-low':
            continue
        best = None
        for prior in kills:
            pa = prior.get('attacker')
            dt = event['t'] - prior['t']
            if prior is event or not pa or pa['weapon'] == 'collateral' or not 0.05 < dt <= COLLATERAL_SECONDS:
                continue
            d = math.dist(event['position'], prior['position'])
            if d <= COLLATERAL_METERS and (best is None or d < best[0]):
                best = (d, prior, pa)
        if best:
            d, prior, pa = best
            event['attacker'] = {
                'unitId': pa['unitId'], 'weapon': 'collateral', 'projectileId': None,
                'missDistance': None, 'launchDistance': None, 'confidence': 'inferred-collateral',
                'afterVictimId': prior['unitId'], 'distanceToEarlierKill': round(d), 'secondsAfter': round(event['t'] - prior['t'], 1),
            }

def mark_player_guns(doc, units, by_id):
    """The player's own gun rounds are NOT recorded as projectile objects (only AI rounds are). A kill with no
    projectile match where the player is close and pointing straight at the victim is probably a player gun kill.
    Validated on Mission 2, where the user confirms guns-only play and all 10 kills fit (<=1.5 km, <=5 degrees)."""
    players = [u for u in units if u.get('isPlayer')]
    if not players:
        return
    player = players[0]
    for event in doc['events']:
        if event.get('type') != 'destroyed' or 'attacker' in event or event['unitId'] not in by_id:
            continue
        victim = by_id[event['unitId']]
        if victim is player:
            continue
        t = event['t']
        now, before = unit_position(player, t), unit_position(player, t - 0.5)
        vpos = unit_position(victim, t - 0.2) or event['position']
        if not now or not before or not vpos:
            continue
        heading = [now[i] - before[i] for i in range(3)]
        to = [vpos[i] - now[i] for i in range(3)]
        n1, n2 = math.hypot(*heading), math.hypot(*to)
        if n1 < 1e-6 or n2 < 1e-6 or n2 > PLAYER_GUN_METERS:
            continue
        cos = max(-1.0, min(1.0, sum(a * b for a, b in zip(heading, to)) / (n1 * n2)))
        angle = math.degrees(math.acos(cos))
        if angle <= PLAYER_GUN_DEGREES:
            event['attacker'] = {
                'unitId': player['id'], 'weapon': 'gun', 'projectileId': None, 'missDistance': None,
                'launchDistance': None, 'confidence': 'inferred-aim', 'distance': round(n2),
                'angleOffHeading': round(angle, 1),
            }


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    sav, js = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    doc = json.loads(js.read_text(encoding='utf-8'))
    found = attribute(doc, projectiles(ac8.Replay(sav)))
    total = sum(1 for e in doc['events'] if e.get('type') == 'destroyed')
    note = 'events[].attacker is inferred from projectile geometry, not a native kill-credit field'
    if note not in doc.setdefault('warnings', []):
        doc['warnings'].append(note)
    js.write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8', newline='')
    print(f'Attributed {found} of {total} destruction events')


if __name__ == '__main__':
    main()

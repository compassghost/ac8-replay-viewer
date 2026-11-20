"""Infer who destroyed whom from projectile tracks (derived, not a native kill-credit field).

Findings this relies on (see FORMAT.md): the replay contains thousands of unlabeled, flag==2 objects whose
translation tracks are projectiles (guns ~1.5 s lifetime, missiles ~20-30 s). A projectile's first sample lies a few
metres from its shooter at launch time; a destroyed unit usually has a projectile within tens of metres at death time.

Usage: python attribute_kills.py Replay3.sav Replay3.json
Adds events[].attacker = {unitId, weapon, projectileId, missDistance, launchDistance, confidence} to destroyed events.
"""
import bisect, json, math, pathlib, struct, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import ac8_replay as ac8

VEHICLE_TYPES = ('Air', 'Naval', 'Ground', 'BuildingParent')
MAX_MISS = 200.0      # metres, projectile to victim at destruction time
MAX_LAUNCH = 60.0     # metres, shooter to projectile first sample
COLLATERAL_SECONDS = 6.0  # weak match this soon after a nearby kill is probably collateral
COLLATERAL_METERS = 450.0
PLAYER_GUN_METERS = 1500.0
PLAYER_GUN_DEGREES = 5.0         # nose-to-victim angle needed when the projectile match is weak or absent
PLAYER_GUN_STRONG_DEGREES = 3.0  # needed to overrule a decent projectile match
PLAYER_GUN_LOOKBACK = 2.0        # seconds before death in which the nose may have been on the victim
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


SHORT_FLIGHT = 1.0        # seconds
BOMB_DROP_METERS = 100.0  # a bomb falls at least this far over its flight
GUN_MUZZLE_SPEED = 750.0  # m/s; gun rounds start at ~850-1600, missiles launch at ~60-700 (measured on Missions 2, 4, 23, 25)
ACCEL_MISSILE = 0.15  # a missile's speed grows by at least this fraction over its flight; gun/cannon rounds hold a constant speed


def weapon_of(f):
    """'missile' if the in-flight projectile accelerates (rocket motor), else 'gun'. Flight time is a poor test: a missile
    fired at close range can hit in under 2 s. Falls back to flight time only when there are too few samples to measure speed."""
    sp = [sum((p - q) ** 2 for p, q in zip(a[1:], b[1:])) ** 0.5 / (b[0] - a[0]) for a, b in zip(f, f[1:]) if b[0] > a[0]]
    if sp and f[-1][0] - f[0][0] < SHORT_FLIGHT and sp[0] >= GUN_MUZZLE_SPEED:
        return 'gun'   # a short flight that starts at gun speed is a gun round; its later speed jumps are sampling noise. A short missile starts slow and accelerates.
    if len(sp) >= 3:
        n = max(1, len(sp) // 3)
        first, last = sum(sp[:n]) / n, sum(sp[-n:]) / n
        if (last - first) / max(first, 1.0) >= ACCEL_MISSILE:
            return 'missile'
        # slow, falling from height and not a gun burst: dropped ordnance (XSDB guided bomb = one projectile; SFFS = a line of them)
        return 'bomb' if sp[0] < GUN_MUZZLE_SPEED and f[0][3] - f[-1][3] >= BOMB_DROP_METERS else 'gun'
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


def victim_position(victim, t, event):
    """Where the victim was at time t: its track for a tracked vehicle, else the recorded death location (components)."""
    if '_times' in victim:
        return unit_position(victim, t)
    return event.get('position')


GUN_BURST_ROUNDS = 3      # a gun kill needs at least this many other gun rounds from the same shooter ...
GUN_BURST_WINDOW = 2.0    # ... launched within this many seconds of the killing round


def start_speed(f):
    return math.dist(f[0][1:], f[1][1:]) / max(f[1][0] - f[0][0], 1e-6)


def nearest_shooter(units, first, exclude_id):
    """(distance, unit) of the unit nearest a projectile's first sample [t, x, y, z], or None."""
    shooter = None
    for u in units:
        if u['startTime'] > first[0] or u['id'] == exclude_id:
            continue
        p = unit_position(u, first[0])
        if not p or p == [0, 0, 0]:
            continue
        d = math.dist(p, first[1:])
        if shooter is None or d < shooter[0]:
            shooter = (d, u)
    return shooter


def gun_burst(units, shooter, pid0, t0, gun_starts, victim_id):
    """True if the shooter also launched GUN_BURST_ROUNDS or more gun-class rounds within GUN_BURST_WINDOW seconds of t0."""
    lo = bisect.bisect_left(gun_starts, (t0 - GUN_BURST_WINDOW,))
    hi = bisect.bisect_left(gun_starts, (t0 + GUN_BURST_WINDOW + 1e-6,))
    n = 0
    for t, pos, pid in gun_starts[lo:hi]:
        if pid == pid0:
            continue
        s = nearest_shooter(units, [t, *pos], victim_id)
        if s and s[0] <= MAX_LAUNCH and s[1] is shooter:
            n += 1
            if n >= GUN_BURST_ROUNDS:
                return True
    return False


def attribute(doc, projs, fire=None):
    units = [u for u in doc['units'] if u['tracks']['position'] and u['iconType'] in VEHICLE_TYPES]
    by_id = {u['id']: u for u in units}
    for u in units:
        u['_times'] = [r[0] for r in u['tracks']['position']]
    # Victims can be ANY unit: components (a ship's guns, AA guns, parts) have no usable world track, so their death location
    # (events[].position) stands in for their position. Only vehicles (those with _times) are tracked through time.
    victims = {u['id']: u for u in doc['units']}
    for event in doc['events']:
        event.pop('attacker', None)   # re-derive everything; stale attributions from an older rule must not survive
    flights = [(pid, rows, in_flight(rows)) for pid, rows in projs]
    flights = [x for x in flights if len(x[2]) >= 2]
    gun_starts = sorted((rows[0][0], rows[0][1:], pid) for pid, rows, f in flights if weapon_of(f) == 'gun')   # launch time and position of every gun-class round
    found = 0
    for event in doc['events']:
        if event.get('type') != 'destroyed' or event['unitId'] not in victims:
            continue
        victim = victims[event['unitId']]
        t = event['t']
        if not victim_position(victim, t, event):
            continue
        # The killing projectile is the one whose flight ENDS at the moment of destruction. Earlier hits that merely
        # damaged the target, and projectiles that only linger after impact, end too early and are skipped.
        best = None
        for pid, rows, f in flights:
            if f[0][0] > t or f[-1][0] < t - MAX_IMPACT_GAP:
                continue
            te = min(t, f[-1][0])
            q = projectile_position(f, te) if te < f[-1][0] else f[-1][1:]
            vp = victim_position(victim, te, event)
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
        shooter = nearest_shooter(units, rows[0], victim['id'])
        if not shooter or shooter[0] > MAX_LAUNCH:
            continue
        weapon = weapon_of(f)
        if weapon == 'gun' and start_speed(f) < GUN_MUZZLE_SPEED and not gun_burst(units, shooter[1], pid, rows[0][0], gun_starts, victim['id']):
            continue   # a lone slow round with no gun burst around it is not evidence of a gun firing: leave the kill unattributed
        event['attacker'] = {
            'unitId': shooter[1]['id'],
            'weapon': weapon,
            'projectileId': pid,
            'missDistance': round(miss, 1),
            'launchDistance': round(shooter[0], 1),
            'impactTime': round(f[-1][0], 2),
            'secondsImpactToDeath': round(gap, 1),
            'confidence': 'inferred-high' if (miss < 50 and abs(gap) <= MAX_IMPACT_GAP) or (miss < 100 and abs(gap) <= 0.5) else 'inferred-low',
        }
        found += 1
    mark_collateral(doc, victims)
    mark_player_guns(doc, units, victims, fire)
    for u in units:
        u.pop('_times', None)
    return found


def mark_collateral(doc, by_id):
    """A weak projectile match shortly after, and near, another attributed kill is probably debris/collision
    with that earlier kill. Re-label it 'collateral' and credit the earlier kill's shooter (still an inference)."""
    kills = [e for e in doc['events'] if e.get('type') == 'destroyed' and e['unitId'] in by_id and e.get('position')]
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

FIRE_AFTER_SECONDS = 1.5    # bullet travel time: a round fired just before release can still land 1.5-2 s after the burst ends
FIRE_AIM_DEGREES = 10.0     # nose-to-victim angle needed while the trigger was down (weak or no projectile match)
FIRE_AIM_DECENT_DEGREES = 5.0


def player_fire_intervals(replay, player_id, duration):
    """The player's trigger, from record type 68 on the player object: a press (first payload byte 1) followed by a release
    (first byte 0). Seen in Missions 1, 2 and 4 with matching press/release counts. Returns [[start, end], ...] or None when
    the recording does not follow that pattern (Missions 23 and 28 do not), so nothing is guessed."""
    ev = []
    for rec in replay.records.values():
        if rec['type'] != 68 or rec['size'] < 24 or rec['payload'] + 4 > rec['size']:
            continue
        if struct.unpack_from('<i', replay.buffer, rec['offset'] + 16)[0] != player_id:
            continue
        t = struct.unpack_from('<f', replay.buffer, rec['offset'] + 12)[0]
        raw = bytes(replay.buffer[rec['offset'] + rec['payload']:rec['offset'] + rec['payload'] + 4])
        ev.append((t, raw))
    ev.sort(key=lambda x: x[0])
    presses = sum(1 for t, r in ev if r[0] == 1 and r != b'\x01\x00\x00\x00')
    releases = sum(1 for t, r in ev if r[0] == 0 and r != b'\x00\x00\x00\x00')
    if presses < 3 or abs(presses - releases) > max(2, 0.2 * presses):
        return None
    out, start = [], None
    for t, r in ev:
        if r[0] == 1 and r != b'\x01\x00\x00\x00':
            if start is None:
                start = t
        elif r[0] == 0 and start is not None:
            out.append([round(start, 3), round(t, 3)])
            start = None
    if start is not None:
        out.append([round(start, 3), round(duration, 3)])
    return out


def firing_at(fire, t):
    """The burst that covers time t (allowing a short tail for rounds in flight), or None."""
    for a, b in fire or []:
        if a - 0.1 <= t <= b + FIRE_AFTER_SECONDS:
            return (a, b)
    return None

def nose_direction(unit, t):
    """The aircraft's forward (+X) axis in world space at time t, from its recorded orientation (None if unknown)."""
    rows = unit['tracks'].get('quaternion') or []
    if not rows:
        return None
    i = bisect.bisect_right([r[0] for r in rows], t) - 1
    x, y, z, w = rows[max(0, min(i, len(rows) - 1))][1:5]
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if n < 1e-9:
        return None
    x, y, z, w = x / n, y / n, z / n, w / n
    # (1,0,0) rotated by q is the first column of its rotation matrix
    return (1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y))


def player_aim(player, victim, event):
    """Smallest angle (degrees) between the player's NOSE and the direction to the victim over the last
    PLAYER_GUN_LOOKBACK seconds before death, restricted to moments within PLAYER_GUN_METERS. Guns fire along the nose,
    which differs from the velocity vector in a turning fight. Returns (angle, distance) or None."""
    t = event['t']
    best = None
    for k in range(int(PLAYER_GUN_LOOKBACK / 0.2) + 1):
        tt = t - 0.2 * k
        me = unit_position(player, tt)
        vp = victim_position(victim, tt, event) or event.get('position')
        nose = nose_direction(player, tt)
        if not me or not vp or not nose:
            continue
        to = [vp[i] - me[i] for i in range(3)]
        d = math.hypot(*to)
        if d < 1e-6 or d > PLAYER_GUN_METERS:
            continue
        cos = max(-1.0, min(1.0, sum(a * b for a, b in zip(nose, to)) / d))
        angle = math.degrees(math.acos(cos))
        if best is None or angle < best[0]:
            best = (angle, d)
    return best


def mark_player_guns(doc, units, by_id, fire=None):
    """The player's own gun rounds are NOT recorded as projectile objects (only AI rounds are), and the save has no
    trigger record. A kill where the player's nose was pointed at the victim shortly before it died, within gun range, is
    inferred to be a player gun kill. Evidence needed depends on what the projectile match offers:
      - no match, or a weak one (low confidence / collateral): nose within PLAYER_GUN_DEGREES
      - a decent match that missed by >= 50 m: nose within PLAYER_GUN_STRONG_DEGREES
      - a close match (< 50 m, high confidence): keep it, and with trigger data note that the player was also firing (playerFiring).
    Validated on Mission 2 (guns-only play): every kill the player reported as a gun kill had the nose within 2.2 degrees at <= 1.5 km."""
    players = [u for u in units if u.get('isPlayer')]
    if not players:
        return
    player = players[0]
    for event in doc['events']:
        if event.get('type') != 'destroyed' or event['unitId'] not in by_id:
            continue
        prior = event.get('attacker')
        if prior and prior['unitId'] == player['id']:
            continue
        victim = by_id[event['unitId']]
        if victim is player:
            continue
        if fire is not None and not firing_at(fire, event['t']):
            continue   # the trigger was up: this was not a player gun kill, however well the nose was lined up
        aim = player_aim(player, victim, event)
        if not aim:
            continue
        angle, dist = aim
        weak_deg, decent_deg = (FIRE_AIM_DEGREES, FIRE_AIM_DECENT_DEGREES) if fire is not None else (PLAYER_GUN_DEGREES, PLAYER_GUN_STRONG_DEGREES)
        if not prior:
            ok, tag = angle <= weak_deg, None
        elif prior['weapon'] == 'collateral' or prior['confidence'] == 'inferred-low':
            ok, tag = angle <= weak_deg, 'weak'
        elif (prior.get('missDistance') or 0) >= 50:
            ok, tag = angle <= decent_deg, 'decent'
        else:
            ok, tag = False, 'strong'
        if ok:
            event['attacker'] = {
                'unitId': player['id'], 'weapon': 'gun', 'projectileId': None, 'missDistance': None,
                'launchDistance': None, 'confidence': 'inferred-aim', 'distance': round(dist),
                'angleOffNose': round(angle, 1),
            }
            if fire is not None:
                event['attacker']['triggerDown'] = True
            if prior:
                event['attacker']['replacedMatch'] = {'unitId': prior['unitId'], 'weapon': prior['weapon'], 'confidence': prior['confidence'], 'missDistance': prior.get('missDistance')}
        elif prior is not None and fire is not None:
            # Someone else is credited, but the player's trigger was down and the victim was within gun range: say so.
            prior['playerFiring'] = {'angleOffNose': round(angle, 1), 'distance': round(dist)}

def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    sav, js = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    doc = json.loads(js.read_text(encoding='utf-8'))
    replay = ac8.Replay(sav)
    players = [u for u in doc['units'] if u.get('isPlayer')]
    fire = player_fire_intervals(replay, players[0]['id'], doc['duration']) if players else None
    found = attribute(doc, projectiles(replay), fire)
    if fire is not None:
        doc['playerFire'] = {'unitId': players[0]['id'], 'intervals': fire, 'source': 'record type 68 on the player object: trigger press/release (inferred meaning)'}
    else:
        doc.pop('playerFire', None)
    total = sum(1 for e in doc['events'] if e.get('type') == 'destroyed')
    note = 'events[].attacker is inferred from projectile geometry, not a native kill-credit field'
    if note not in doc.setdefault('warnings', []):
        doc['warnings'].append(note)
    js.write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8', newline='')
    print(('Trigger data: %d bursts. ' % len(fire) if fire is not None else 'No usable trigger data. ') + f'Attributed {found} of {total} destruction events')


if __name__ == '__main__':
    main()

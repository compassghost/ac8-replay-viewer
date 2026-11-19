"""Round an exported replay JSON in place to shrink it (the .sav files are never touched; exports can be regenerated).

Precision: timestamps 3 decimals (ms), positions 2 decimals (cm), quaternion components 4 decimals (~0.006 degrees).
Only unit tracks are rounded; annotations, events, attribution and missiles are left exactly as they are.
The full-precision file is kept next to it as <name>.full-precision.json.bak unless --no-backup is given.

Usage: python round_export.py Replay3.json [--no-backup]
"""
import json, pathlib, shutil, sys

T, POS, QUAT = 3, 2, 4


def rounded(rows, decimals):
    """rows: [t, a, b, ..., step]; round t to T decimals and the float components (everything between t and a trailing 0/1 step flag)."""
    out = []
    for r in rows:
        r = list(r)
        r[0] = round(r[0], T)
        for i in range(1, len(r)):
            if isinstance(r[i], float):
                r[i] = round(r[i], decimals)
        out.append(r)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = pathlib.Path(args[0])
    doc = json.loads(path.read_text(encoding='utf-8'))
    before = path.stat().st_size
    if '--no-backup' not in sys.argv:
        backup = path.with_name(path.stem + '.full-precision.json.bak')
        if backup.exists():
            raise SystemExit(f'{backup.name} already exists; refusing to overwrite it.')
        shutil.copy2(path, backup)
    for u in doc['units']:
        tr = u['tracks']
        tr['position'] = rounded(tr['position'], POS)
        tr['relativePosition'] = rounded(tr['relativePosition'], POS)
        tr['quaternion'] = rounded(tr['quaternion'], QUAT)
        tr['relativeQuaternion'] = rounded(tr['relativeQuaternion'], QUAT)
        if u.get('startTime') is not None:
            u['startTime'] = round(u['startTime'], T)
    note = f'unit tracks rounded: time {T} dp, position {POS} dp (m), quaternion {QUAT} dp (round_export.py)'
    if note not in doc.setdefault('warnings', []):
        doc['warnings'].append(note)
    path.write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8', newline='')
    after = path.stat().st_size
    print(f'{path.name}: {before / 1048576:.1f} MB -> {after / 1048576:.1f} MB ({after / before * 100:.0f}%)')


if __name__ == '__main__':
    main()

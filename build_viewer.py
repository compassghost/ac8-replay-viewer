"""Build reference-viewer.html from viewer.template.html + playback.mjs.

By default no replay is embedded (the page is ~0.2 MB) and the viewer loads replays.json and the selected export over HTTP.
Pass --embed [Replay3.json] to make a self-contained copy that also works from file:// (large: the embedded export is ~80 MB).
"""
import argparse,pathlib
root=pathlib.Path(__file__).parent
ap=argparse.ArgumentParser()
ap.add_argument('--embed',nargs='?',const='Replay3.json',default=None,metavar='REPLAY.json',help='embed this export in the page (default off)')
ap.add_argument('--sample',dest='embed',metavar='REPLAY.json',help=argparse.SUPPRESS)  # old spelling of --embed
ap.add_argument('--out',default='reference-viewer.html')
args=ap.parse_args()
sample=(root/args.embed).read_text(encoding='utf-8').replace('<','\\u003c') if args.embed else ''
html=(root/'viewer.template.html').read_text(encoding='utf-8').replace('__SAMPLE_JSON__',sample).replace('__PLAYBACK_CODE__',(root/'playback.mjs').read_text(encoding='utf-8').replace('export function','function'))
(root/args.out).write_text(html,encoding='utf-8')
print(('Built reference viewer with embedded '+args.embed) if args.embed else 'Built reference viewer (no embedded replay; loads replays.json over HTTP).')

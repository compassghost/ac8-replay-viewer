// Headless, deterministic replay video renderer.
// Steps replay time frame by frame (speed/fps seconds of replay per video frame), screenshots the viewer's own canvas
// in headless Edge/Chrome, and pipes the frames to ffmpeg. No real-time dependence, no visible browser window.
//
//   node render_video.mjs ..\Replay3.json [--speed 20] [--fps 30] [--size 800x800] [--view 3d|top] [--crop 0.8] [--camera whole|dynamic|player|selected|target --unit id [--target lockedId]] [--plates player,wingmen,...] [--missiles] [--components] [--component-kills] [--frame x0,y0,x1,y1] [--yaw deg --elevation deg] [--zoom z]
//                         [--from 0] [--to 2067.9] [--out out.mp4] [--crf 24] [--browser path\to\msedge.exe]
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import puppeteer from 'puppeteer-core';
import ffmpegPath from 'ffmpeg-static';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const args = process.argv.slice(2);
const opt = (name, fallback) => { const i = args.indexOf('--' + name); return i >= 0 ? args[i + 1] : fallback; };
const input = args.find((a, i) => !a.startsWith('--') && !(i > 0 && args[i - 1].startsWith('--')));
if (!input) { console.error('Usage: node render_video.mjs <replay.json> [--speed 20] [--fps 30] [--size 800x800] [--view 3d|top] [--from s] [--to s] [--out file.mp4]'); process.exit(2); }

const speed = Number(opt('speed', 20)), fps = Number(opt('fps', 30)), crf = opt('crf', '18'), view = opt('view', '3d');
// whole mission (default), the combat-fitting dynamic camera, follow the player, or follow a selected unit (--unit <id>)
const camera = ({ dynamic: 'dynamic', player: 'player', selected: 'selected', target: 'target' })[opt('camera', 'whole')] ?? 'off';
const unitId = opt('unit', null) == null ? null : Number(opt('unit'));
if ((camera === 'selected' || camera === 'target') && !Number.isInteger(unitId)) { console.error('--camera ' + camera + ' needs --unit <object id>'); process.exit(2); }
const lockTarget = opt('target', null) == null ? null : Number(opt('target'));
// Nameplates: comma list of player,wingmen,namedAllies,alliedUnits,namedEnemies,enemyUnits (default: viewer default = player,wingmen)
const plates = opt('plates', null)?.split(',').filter(Boolean) ?? null;
const crop = Number(opt('crop', camera === 'off' ? 0.8 : 1)); // fraction of the whole-mission frame kept, centred (0.8 = central 80%)
if (!(crop > 0.1 && crop <= 1)) { console.error('--crop must be between 0.1 and 1'); process.exit(2); }
// --frame x0,y0,x1,y1: a rectangle in view-plane metres (copy it from the viewer's Capture panel, with --yaw/--elevation in degrees).
// It overrides --crop/--camera; the output size follows the rectangle's aspect ratio (longest side 800).
const frameArg = opt('frame', null)?.split(',').map(Number) ?? null;
if (frameArg && (frameArg.length !== 4 || frameArg.some(v => !Number.isFinite(v)) || frameArg[2] <= frameArg[0] || frameArg[3] <= frameArg[1])) { console.error('--frame needs x0,y0,x1,y1 with x1>x0 and y1>y0'); process.exit(2); }
const frame = frameArg && { x0: frameArg[0], y0: frameArg[1], x1: frameArg[2], y1: frameArg[3] };
const rad = name => opt(name, null) == null ? null : Number(opt(name)) * Math.PI / 180;
const yaw = rad('yaw'), elevation = rad('elevation');
// --zoom z: viewer zoom factor (1 = default framing, >1 closer); overrides --crop. Ignored with --frame.
const zoom = opt('zoom', null) == null ? null : Number(opt('zoom'));
if (zoom != null && !(zoom >= 0.2 && zoom <= 12)) { console.error('--zoom must be between 0.2 and 12'); process.exit(2); }
const frameSize = frame ? (() => { const fw = frame.x1 - frame.x0, fh = frame.y1 - frame.y0, k = 800 / Math.max(fw, fh); return `${Math.max(200, 2 * Math.round(fw * k / 2))}x${Math.max(200, 2 * Math.round(fh * k / 2))}`; })() : '800x450'; // default output is 16:9; a drawn frame keeps its own aspect
const [W, H] = opt('size', frameSize).split('x').map(Number);
if (!(W >= 200 && W <= 800 && H >= 200 && H <= 800)) { console.error('--size must be between 200x200 and 800x800'); process.exit(2); }
const browserPath = opt('browser', [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
].find(p => fs.existsSync(p)));
if (!browserPath) { console.error('No Edge/Chrome found; pass --browser <path>'); process.exit(2); }

// Build a throwaway viewer page around the requested replay (same template/playback code as build_viewer.py).
const jsonPath = path.resolve(input);
const doc = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
const html = fs.readFileSync(path.join(root, 'viewer.template.html'), 'utf8')
  .replace('__SAMPLE_JSON__', () => fs.readFileSync(jsonPath, 'utf8').replaceAll('<', '\\u003c'))
  .replace('__PLAYBACK_CODE__', () => fs.readFileSync(path.join(root, 'playback.mjs'), 'utf8').replaceAll('export function', 'function'));
const pagePath = path.join(os.tmpdir(), `replay-render-${process.pid}.html`);
fs.writeFileSync(pagePath, html, 'utf8');

const missionNumber = doc.mission.MissionID - 1;
const out = path.resolve(opt('out', path.join(root, `M${missionNumber}-${path.basename(jsonPath, '.json')}-${speed}x.mp4`)));

const browser = await puppeteer.launch({ executablePath: browserPath, headless: 'new', args: ['--hide-scrollbars', '--force-device-scale-factor=1'] });
let ffmpeg;
try {
  const page = await browser.newPage();
  page.on('pageerror', e => console.error('page error:', e.message));
  // Canvas fills .map = (viewport width - 280 sidebar) x (viewport height - 181 header/footer).
  await page.setViewport({ width: W + 280, height: H + 181, deviceScaleFactor: 1 });
  await page.goto(pathToFileURL(pagePath).href, { waitUntil: 'load', timeout: 300000 });
  await page.waitForFunction('window.replayApi', { timeout: 300000 });
  const size = await page.evaluate(`replayApi.setup(${JSON.stringify({ view, speed, crop, follow: camera, unit: unitId, lockTarget, plates, missiles: args.includes('--missiles'), components: args.includes('--components'), componentKills: args.includes('--component-kills'), frame, yaw, elevation, zoom })})`);
  if (size.w !== W || size.h !== H) console.warn(`Canvas is ${size.w}x${size.h}, expected ${W}x${H}; output uses the canvas size.`);
  const duration = await page.evaluate('replayApi.duration()');
  const from = Number(opt('from', 0)), to = Math.min(Number(opt('to', duration)), duration);
  const step = speed / fps, frames = Math.floor((to - from) / step) + 1;
  console.log(`M${missionNumber} (Mission ID ${doc.mission.MissionID}): ${from.toFixed(1)}-${to.toFixed(1)} s at ${speed}x -> ${frames} frames, ${(frames / fps).toFixed(1)} s video, ${size.w}x${size.h}`);

  ffmpeg = spawn(ffmpegPath, ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'png', '-i', '-',
    '-c:v', 'libx264', '-preset', 'slow', '-tune', 'animation', '-crf', crf, '-pix_fmt', 'yuv420p', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  const done = new Promise((res, rej) => { ffmpeg.on('close', c => c === 0 ? res() : rej(new Error('ffmpeg exited with ' + c))); ffmpeg.on('error', rej); });
  ffmpeg.stdin.on('error', () => {});

  const started = Date.now();
  for (let i = 0; i < frames; i++) {
    const url = await page.evaluate(`replayApi.frame(${from + i * step}, 'png')`);
    const buf = Buffer.from(url.slice(url.indexOf(',') + 1), 'base64');
    if (!ffmpeg.stdin.write(buf)) await new Promise(r => ffmpeg.stdin.once('drain', r));
    if (i % 100 === 0 || i === frames - 1) {
      const el = (Date.now() - started) / 1000;
      console.log(`frame ${i + 1}/${frames} (${((i + 1) / frames * 100).toFixed(0)}%), ${el.toFixed(0)} s elapsed, ~${(el / (i + 1) * (frames - i - 1)).toFixed(0)} s left`);
    }
  }
  ffmpeg.stdin.end();
  await done;
  console.log(`Wrote ${out} (${(fs.statSync(out).size / 1048576).toFixed(1)} MB)`);
} finally {
  await browser.close();
  fs.rmSync(pagePath, { force: true });
}
